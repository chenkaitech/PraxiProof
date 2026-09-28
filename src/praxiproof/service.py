import hashlib
import json
import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxiproof.compiler.agent_skill import build_skill_ir, write_skill, zip_dir
from praxiproof.config import Settings, save_overrides, validate_changes
from praxiproof.constraints.compiler import compile_requirements
from praxiproof.constraints.engine import evaluate
from praxiproof.constraints.schema import ConstraintType
from praxiproof.document.extract import ExtractedDocument, extract
from praxiproof.ir.evidence import Evidence, VideoLocator, format_timestamp
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import RequirementSet
from praxiproof.ir.verification import Status, Verdict, VerificationReport
from praxiproof.llm import LLM, LLMError
from praxiproof.store import NotFound, Store
from praxiproof.verifier.aligner import align, llm_matcher
from praxiproof.verifier.evidence import traceability
from praxiproof.video.backend import VideoBackend, get_backend
from praxiproof.video.frames import FFmpegError, frame_at, probe

log = logging.getLogger(__name__)

_VIOLATION_KIND = {
    ConstraintType.MUST_HAVE: "Missing Step",
    ConstraintType.MAX_INTERVAL: "Timing Violation",
    ConstraintType.BEFORE: "Order Violation",
    ConstraintType.AFTER: "Order Violation",
    ConstraintType.PRECONDITION: "Order Violation",
    ConstraintType.MUST_NOT: "Prohibited Action",
    ConstraintType.COUNT: "Count Violation",
}
_SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2}
_PRESENCE_RULES = (ConstraintType.MUST_HAVE, ConstraintType.BEFORE, ConstraintType.AFTER, ConstraintType.PRECONDITION)


def violation_kind(verdict: Verdict) -> str:
    if verdict.status != Status.VIOLATION:
        return "Needs Evidence"
    if verdict.constraint.type in _PRESENCE_RULES and not verdict.observed_event_ids:
        return "Missing Step"
    return _VIOLATION_KIND[verdict.constraint.type]


class PraxiProof:
    def __init__(
        self,
        settings: Settings,
        llm: LLM,
        store: Store | None = None,
        backend_factory: Callable[[], VideoBackend] | None = None,
        vlm: LLM | None = None,
    ):
        self.settings = settings
        self.llm = llm
        self.vlm = vlm or llm  # sees the video frames; may be a different provider than the text model
        self.data_dir = settings.data_dir
        for sub in ("manuals", "videos", "skills", "frames"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
        self.store = store or Store(self.data_dir / "praxiproof.db")
        self._backend_factory = backend_factory or (lambda: get_backend(self.settings, self.llm, self.vlm))

    def update_settings(self, changes: dict[str, Any], models: list[dict[str, Any]] | None) -> Settings:
        clean = validate_changes(changes, models, llm_in_models=self.settings.llm_provider == "ollama")
        updated = replace(self.settings, **clean)
        if updated.video_backend == "nvidia_sop" and not updated.sop_bp_url:
            raise ValueError("sop_bp_url is required for the nvidia_sop video backend")
        if updated.video_backend == "ddm_vlm" and not updated.ddm_checkpoint:
            raise ValueError("ddm_checkpoint is required for the ddm_vlm video backend")
        save_overrides(updated)
        self.settings = updated
        return updated

    def recover_interrupted(self) -> int:
        """Jobs run in this process, so anything still queued or processing after a restart will never finish."""
        fixed = 0
        for table in ("manuals", "runs", "pipelines"):
            for record in self.store.list(table, limit=1_000_000):
                if record.get("status") in ("queued", "processing"):
                    self.store.update(table, record["id"], status="failed", stage=None, error="interrupted by a service restart; start it again")
                    fixed += 1
        if fixed:
            log.warning("marked %d interrupted job(s) as failed after restart", fixed)
        return fixed

    def prune_uploads(self, max_age_seconds: float = 3600) -> int:
        """Accepted uploads are moved into manuals/ or videos/; whatever is left here belongs to an aborted request."""
        uploads, cutoff, removed = self.data_dir / "uploads", time.time() - max_age_seconds, 0
        for path in uploads.glob("*") if uploads.is_dir() else []:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def add_manual(self, upload: Path, filename: str, procedure: str | None) -> dict[str, Any]:
        record = self.store.create(
            "manuals", {"filename": filename, "procedure_hint": procedure, "status": "queued", "error": None}
        )
        target = self.data_dir / "manuals" / f"{record['id']}{Path(filename).suffix.lower()}"
        shutil.move(upload, target)
        return self.store.update("manuals", record["id"], path=str(target))

    def process_manual(self, manual_id: str) -> None:
        record = self.store.update("manuals", manual_id, status="processing")
        try:
            doc = extract(Path(record["path"]), manual_id)
            self.store.update("manuals", manual_id, sha256=doc.sha256, page_count=doc.page_count, extractor=doc.extractor)
            (self.data_dir / "manuals" / f"{manual_id}.document.json").write_text(doc.model_dump_json(), encoding="utf-8")
            result = compile_requirements(doc, self.llm, self.settings.llm_model, record.get("procedure_hint"))
            self.store.put_evidence(result.evidence)
            rs = result.requirement_set
            if not rs.requirements:
                # A run against zero rules would vacuously report PASS — never let that look like a verification.
                rejected = f" ({len(result.rejected)} candidate rule(s) were rejected as invalid)" if result.rejected else ""
                raise ValueError(f"no verifiable rules could be extracted from this manual{rejected}; try another model or recompile")
            if len(result.rejected) > len(rs.requirements):
                # Verifying against the few rules that survived would let almost anything pass, so this is not "ready".
                raise ValueError(
                    f"only {len(rs.requirements)} of {len(rs.requirements) + len(result.rejected)} candidate rules were valid "
                    f"(most were rejected: {result.rejected[0].error[:120]}); recompile or try another model"
                )
            self.store.update(
                "manuals",
                manual_id,
                status="ready",
                procedure=rs.procedure,
                requirement_set=rs.model_dump(mode="json"),
                rejected=[r.model_dump() for r in result.rejected],
                repaired=result.repaired,
                blocks_used=result.blocks_used,
                counts=_manual_counts(rs),
            )
        except (LLMError, ValueError, OSError) as exc:
            log.exception("manual %s failed", manual_id)
            self.store.update("manuals", manual_id, status="failed", error=str(exc)[:500])

    def document(self, manual_id: str) -> ExtractedDocument:
        path = self.data_dir / "manuals" / f"{manual_id}.document.json"
        return ExtractedDocument.model_validate_json(path.read_text(encoding="utf-8"))

    def requirement_set(self, manual_id: str) -> RequirementSet:
        record = self.store.get("manuals", manual_id)
        if record.get("status") != "ready":
            raise ValueError(f"manual {manual_id} is not ready (status: {record.get('status')})")
        return RequirementSet.model_validate(record["requirement_set"])

    def add_video(self, upload: Path, filename: str, note: str | None = None) -> dict[str, Any]:
        meta = probe(upload)
        record = self.store.create("videos", {"filename": filename, "meta": meta.model_dump(), "note": (note or "").strip() or None})
        target = self.data_dir / "videos" / f"{record['id']}{Path(filename).suffix.lower() or '.mp4'}"
        shutil.move(upload, target)
        size = target.stat().st_size
        return self.store.update("videos", record["id"], path=str(target), size_bytes=size)

    def discard_video(self, video_id: str) -> None:
        """Undo add_video: used when a video was saved but a later step in the same request failed, so the
        request as a whole should leave no trace (see start_pipeline in app.py)."""
        try:
            record = self.store.get("videos", video_id)
        except NotFound:
            return
        Path(record["path"]).unlink(missing_ok=True)
        self.store.delete("videos", video_id)

    def frame(self, video_id: str, seconds: float) -> bytes:
        key = self.data_dir / "frames" / f"{video_id}-{seconds:.1f}.jpg"
        if not key.exists():
            key.write_bytes(frame_at(Path(self.store.get("videos", video_id)["path"]), seconds, 480))
        return key.read_bytes()

    def create_run(
        self, manual_id: str, video_id: str | None, observation: dict[str, Any] | None, label: str | None, external: bool = False
    ) -> dict[str, Any]:
        manual = self.store.get("manuals", manual_id)
        if manual.get("status") != "ready":
            raise ValueError(f"manual {manual_id} is not ready")
        if (video_id is None) == (observation is None):
            raise ValueError("provide exactly one of video_id or observation")
        video_name = label
        if video_id:
            video_name = self.store.get("videos", video_id)["filename"]
        else:
            Observation.model_validate(observation)
        return self.store.create(
            "runs",
            {
                "manual_id": manual_id,
                "manual_name": manual["filename"],
                "procedure": manual.get("procedure"),
                "video_id": video_id,
                "video_name": video_name or "observation.json",
                "input_observation": observation,
                # True only for a caller-supplied observation posted straight to the API (not a video_id run,
                # not a demo fixture): its evidence is tagged "external_observation", not "video".
                "external_observation": external,
                "status": "queued",
                "stage": None,
                "error": None,
            },
        )

    def process_run(self, run_id: str) -> None:
        run = self.store.update("runs", run_id, status="processing", stage="observing")
        try:
            requirements = self.requirement_set(run["manual_id"])
            if run["video_id"]:
                video = self.store.get("videos", run["video_id"])
                observation, video_evidence = self._backend_factory().observe(
                    Path(video["path"]), run["video_id"], requirements.events, requirements.procedure
                )
            else:
                observation, video_evidence = observation_with_evidence(
                    run["input_observation"], run_id, external=bool(run.get("external_observation"))
                )
            self.store.put_evidence(video_evidence)

            self.store.update("runs", run_id, stage="aligning")
            try:
                observation, alignment = align(observation, requirements.events, llm_matcher(self.llm, self.settings.llm_model))
            except LLMError:
                log.warning("label matching model unavailable for run %s; aligning by exact label only", run_id)
                observation, alignment = align(observation, requirements.events, None)

            self.store.update("runs", run_id, stage="verifying")
            verdicts = evaluate(requirements, observation, self.settings.min_confidence)
            report = VerificationReport(
                run_id=run_id,
                manual_id=run["manual_id"],
                video_id=run["video_id"],
                procedure=requirements.procedure,
                verdicts=verdicts,
                alignment=alignment,
            )
            self._finish_run(run_id, report, observation, requirements)
        except (LLMError, ValueError, OSError, FFmpegError) as exc:
            log.exception("run %s failed", run_id)
            self.store.update("runs", run_id, status="failed", stage=None, error=str(exc)[:500])

    def _finish_run(self, run_id: str, report: VerificationReport, observation: Observation, requirements: RequirementSet) -> None:
        evidence = self._report_evidence(report)
        ratio, issues = traceability(report, evidence)
        self.store.update(
            "runs",
            run_id,
            status="done",
            stage=None,
            observation=observation.model_dump(mode="json"),
            report=report.model_dump(mode="json"),
            metrics=run_metrics(report, observation, requirements, ratio, self.settings.min_confidence),
            traceability_issues=issues,
            **_result_summary(report),
        )

    def report(self, run_id: str) -> VerificationReport:
        run = self.store.get("runs", run_id)
        if run.get("status") != "done":
            raise ValueError(f"run {run_id} is not finished (status: {run.get('status')})")
        return VerificationReport.model_validate(run["report"])

    def _report_evidence(self, report: VerificationReport) -> dict[str, Evidence]:
        ids = [e for v in report.verdicts for e in v.requirement_evidence_ids + v.observation_evidence_ids]
        return self.store.evidence(ids)

    def review(self, run_id: str, rule_id: str, decision: str | None) -> dict[str, Any]:
        report = self.report(run_id)
        verdict = next((v for v in report.verdicts if v.rule_id == rule_id), None)
        if verdict is None:
            raise ValueError(f"{rule_id} is not part of run {run_id}")
        verdict.review = decision
        return self.store.update("runs", run_id, report=report.model_dump(mode="json"), **_result_summary(report))

    def create_pipeline(
        self, manual_id: str, video_id: str | None, observation: dict[str, Any] | None, label: str | None
    ) -> dict[str, Any]:
        manual = self.store.get("manuals", manual_id)
        if (video_id is None) == (observation is None):
            raise ValueError("provide exactly one of video_id or observation")
        video_name = self.store.get("videos", video_id)["filename"] if video_id else (label or "observation.json")
        if observation is not None:
            Observation.model_validate(observation)
        return self.store.create(
            "pipelines",
            {
                "manual_id": manual_id,
                "manual_name": manual["filename"],
                "video_id": video_id,
                "video_name": video_name,
                "input_observation": observation,
                "status": "queued",
                "stage": None,
                "run_id": None,
                "skill_id": None,
                "error": None,
            },
        )

    def process_pipeline(self, pipeline_id: str) -> None:
        pipeline = self.store.update("pipelines", pipeline_id, status="processing", stage="compiling")
        try:
            manual_id = pipeline["manual_id"]
            if self.store.get("manuals", manual_id).get("status") != "ready":
                self.process_manual(manual_id)
                manual = self.store.get("manuals", manual_id)
                if manual.get("status") != "ready":
                    raise ValueError(f"manual {manual_id} failed to compile: {manual.get('error')}")

            self.store.update("pipelines", pipeline_id, stage="verifying")
            run = self.create_run(manual_id, pipeline["video_id"], pipeline["input_observation"], pipeline["video_name"])
            self.store.update("pipelines", pipeline_id, run_id=run["id"])
            self.process_run(run["id"])
            run = self.store.get("runs", run["id"])
            if run.get("status") != "done":
                raise ValueError(f"verification run {run['id']} failed: {run.get('error')}")

            self.store.update("pipelines", pipeline_id, stage="packaging")
            skill = self.compile_skill(run["id"])
            self.store.update("pipelines", pipeline_id, status="done", stage=None, skill_id=skill["id"], result=run.get("result"))
        except (ValueError, NotFound, OSError) as exc:
            log.exception("pipeline %s failed", pipeline_id)
            self.store.update("pipelines", pipeline_id, status="failed", error=str(exc)[:500])

    def approve_skill(self, skill_id: str) -> dict[str, Any]:
        self.store.get("skills", skill_id)
        return self.store.update("skills", skill_id, review_status="approved", reviewed_at=datetime.now(UTC).isoformat(timespec="seconds"))

    def compile_skill(self, run_id: str) -> dict[str, Any]:
        run = self.store.get("runs", run_id)
        report = self.report(run_id)
        requirements = self.requirement_set(run["manual_id"])
        observation = Observation.model_validate(run["observation"])
        skill = build_skill_ir(requirements, report, observation)
        evidence = self._report_evidence(report)
        record = self.store.create("skills", {"run_id": run_id, "name": skill.name, "procedure": requirements.procedure})
        out_dir = self.data_dir / "skills" / record["id"]
        root = write_skill(skill, requirements, report, evidence, out_dir, self._violation_keyframes(report, evidence), observation)
        return self.store.update(
            "skills",
            record["id"],
            path=str(root),
            skill=skill.model_dump(mode="json"),
            verification_summary=report.counts(),
            review_status="pending",
        )

    def _violation_keyframes(self, report: VerificationReport, evidence: dict[str, Evidence]) -> dict[str, bytes]:
        if not report.video_id:
            return {}
        frames = {}
        for v in report.verdicts:
            if v.status != Status.VIOLATION:
                continue
            for eid in v.observation_evidence_ids:
                loc = evidence[eid].locator if eid in evidence else None
                if isinstance(loc, VideoLocator):
                    try:
                        frames[f"{v.rule_id.lower()}-{format_timestamp(loc.start).replace(':', 'm')}s.jpg"] = self.frame(report.video_id, loc.start)
                    except FFmpegError:
                        log.warning("could not extract keyframe for %s", eid)
        return frames

    def skill_markdown(self, skill_id: str) -> str:
        return (Path(self.store.get("skills", skill_id)["path"]) / "SKILL.md").read_text(encoding="utf-8")

    def skill_zip(self, skill_id: str) -> tuple[str, bytes]:
        record = self.store.get("skills", skill_id)
        return record["name"], zip_dir(Path(record["path"]))

    def finding_details(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        report = VerificationReport.model_validate(run["report"])
        evidence = self._report_evidence(report)
        findings = []
        for v in sorted(report.verdicts, key=lambda v: (v.status != Status.VIOLATION, _SEVERITY_RANK[v.severity])):
            if v.status == Status.PASS:
                continue
            manual = [evidence[e] for e in v.requirement_evidence_ids if e in evidence]
            video = [evidence[e] for e in v.observation_evidence_ids if e in evidence]
            findings.append(
                {
                    "run_id": run["id"],
                    "video_id": run.get("video_id"),
                    "video_name": run.get("video_name"),
                    "rule_id": v.rule_id,
                    "status": v.status,
                    "severity": v.severity,
                    "category": v.category,
                    "kind": violation_kind(v),
                    "statement": v.statement,
                    "reason": v.reason,
                    "reason_code": v.reason_code,
                    "reason_params": v.reason_params,
                    "measured": v.measured,
                    "needed_evidence": v.needed_evidence,
                    "needed_code": v.needed_code,
                    "review": v.review,
                    "constraint": v.constraint.signature(),
                    "manual": [{"citation": e.citation(), "text": e.text, "evidence_id": e.evidence_id} for e in manual],
                    "video": [
                        {"citation": e.citation(), "start": e.locator.start, "end": e.locator.end, "evidence_id": e.evidence_id, "text": e.text}
                        for e in video
                        if isinstance(e.locator, VideoLocator)
                    ],
                }
            )
        return findings

    def dashboard(self) -> dict[str, Any]:
        runs = self.store.list("runs", limit=50)
        done = [r for r in runs if r.get("status") == "done"]
        latest = done[0] if done else None
        manual = self.store.list("manuals", limit=1)
        video = self.store.list("videos", limit=1)
        return {
            "latest_manual": manual[0] if manual else None,
            "latest_video": video[0] if video else None,
            "latest_run": _run_row(latest) if latest else None,
            "metrics": latest.get("metrics") if latest else None,
            "recent_runs": [_run_row(r) for r in runs[:10]],
            "findings": self.finding_details(latest)[:5] if latest else [],
        }


def _manual_counts(rs: RequirementSet) -> dict[str, int]:
    return {
        "rules": len(rs.requirements),
        "safety_rules": sum(r.category == "safety" for r in rs.requirements),
        "steps": len(rs.events),
        "critical": sum(r.severity == "critical" for r in rs.requirements),
    }


def _result_summary(report: VerificationReport) -> dict[str, Any]:
    active = [v for v in report.verdicts if v.review != "rejected"]
    violations = [v for v in active if v.status == Status.VIOLATION]
    counts = {s.value: sum(v.status == s for v in active) for s in Status}
    if violations:
        worst = min(violations, key=lambda v: _SEVERITY_RANK[v.severity])
        result = violation_kind(worst)
    elif counts["UNVERIFIED"] or counts["INSUFFICIENT_EVIDENCE"]:
        result = "Needs Evidence"
    else:
        result = "PASS"
    return {"result": result, "violations": len(violations), "counts": counts}


def run_metrics(
    report: VerificationReport, observation: Observation, requirements: RequirementSet, trace_ratio: float, min_confidence: float
) -> dict[str, Any]:
    verdicts = report.verdicts
    safety = [v for v in verdicts if v.category == "safety"]
    decided_safety = [v for v in safety if v.status in (Status.PASS, Status.VIOLATION)]
    seen_labels = {e.label for e in observation.events if e.confidence >= min_confidence}
    steps_seen = [e for e in requirements.events if e.label in seen_labels]
    aligned = [a for a in report.alignment if a["method"] != "unmatched"]
    return {
        "evidence_traceability": {"value": round(trace_ratio, 3), "numerator": round(trace_ratio * len(verdicts)), "denominator": len(verdicts)},
        "safety_coverage": {
            "value": round(len(decided_safety) / len(safety), 3) if safety else 1.0,
            "numerator": len(decided_safety),
            "denominator": len(safety),
        },
        "step_coverage": {
            "value": round(len(steps_seen) / len(requirements.events), 3) if requirements.events else 1.0,
            "numerator": len(steps_seen),
            "denominator": len(requirements.events),
        },
        "observation_alignment": {
            "value": round(len(aligned) / len(report.alignment), 3) if report.alignment else 1.0,
            "numerator": len(aligned),
            "denominator": len(report.alignment),
        },
        "violations": sum(v.status == Status.VIOLATION for v in verdicts),
        "counts": report.counts(),
    }


def _run_row(run: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "created_at", "manual_id", "manual_name", "video_id", "video_name", "procedure", "status", "stage", "error", "result", "violations", "counts")
    return {k: run.get(k) for k in keys}


def observation_with_evidence(data: dict[str, Any], run_id: str, external: bool = False) -> tuple[Observation, list[Evidence]]:
    """external=True marks events that did not come from a video file processed by our own backends: a
    caller posted this observation JSON directly to /api/runs. Demo fixtures (external=False) are trusted,
    server-controlled data standing in for a video; a client-submitted observation is not, and should not be
    displayed or traced as if it were camera evidence (see traceability(), agent_skill.py, widgets.js)."""
    observation = Observation.model_validate(data)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    evidence, events = [], []
    for event in observation.events:
        item = Evidence(
            evidence_id=event.evidence_id or f"EV-{run_id}-{event.event_id}",
            source_type="external_observation" if external else "video",
            source_id=observation.source_id,
            sha256=digest,
            locator=VideoLocator(start=event.start, end=event.end),
            text=event.description or event.label,
            extractor=observation.backend,
            model=observation.model,
            confidence=event.confidence,
        )
        evidence.append(item)
        events.append(event.model_copy(update={"evidence_id": item.evidence_id}))
    return observation.model_copy(update={"events": events}), evidence
