import io
import json
import re
import zipfile
from collections.abc import Mapping
from pathlib import Path

from praxiproof.constraints.schema import ConstraintType
from praxiproof.ir.evidence import Evidence
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import RequirementSet
from praxiproof.ir.skill import SkillIR, SkillRule, SkillStep
from praxiproof.ir.verification import Status, VerificationReport


def slugify(text: str, limit: int = 64) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].rstrip("-") or "procedure"


def build_skill_ir(requirements: RequirementSet, report: VerificationReport, observation: Observation | None) -> SkillIR:
    first_seen: dict[str, float] = {}
    if observation:
        for event in observation.sorted_events():
            first_seen.setdefault(event.label, event.start)
    seen_in_time_order = iter(sorted((e for e in requirements.events if e.label in first_seen), key=lambda e: first_seen[e.label]))
    ordered = [next(seen_in_time_order) if e.label in first_seen else e for e in requirements.events]

    def rule(req) -> SkillRule:
        return SkillRule(
            rule_id=req.rule_id,
            statement=req.statement,
            constraint=req.constraint.signature(),
            severity=req.severity,
            category=req.category,
            evidence_ids=req.evidence_ids,
        )

    steps = [
        SkillStep(
            event=e.label,
            instruction=e.description,
            evidence_ids=sorted({eid for r in requirements.requirements if e.label in r.constraint.events() for eid in r.evidence_ids}),
        )
        for e in ordered
    ]
    preconditions = [rule(r) for r in requirements.requirements if r.constraint.type == ConstraintType.PRECONDITION]
    rules = [rule(r) for r in requirements.requirements if r.constraint.type != ConstraintType.PRECONDITION]
    critical = sum(r.severity == "critical" for r in requirements.requirements)
    description = (
        f"Guide a technician through {requirements.procedure} and check the work against "
        f"{len(requirements.requirements)} rules compiled from the official manual ({critical} critical). "
        f"Use when planning, performing, or reviewing this procedure."
    )
    return SkillIR(
        name=slugify(requirements.procedure),
        description=description[:1024],
        goal=f"Complete {requirements.procedure} exactly as the manual requires.",
        preconditions=preconditions,
        steps=steps,
        rules=rules,
        verified_by_run=report.run_id,
        verification_summary=report.counts(),
    )


def write_skill(
    skill: SkillIR,
    requirements: RequirementSet,
    report: VerificationReport,
    evidence: Mapping[str, Evidence],
    out_dir: Path,
    keyframes: Mapping[str, bytes] | None = None,
) -> Path:
    root = out_dir / skill.name
    for sub in ("references", "evals", "assets"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    (root / "SKILL.md").write_text(_skill_md(skill, report, evidence), encoding="utf-8")
    (root / "references" / "requirements.json").write_text(requirements.model_dump_json(indent=2), encoding="utf-8")
    (root / "references" / "evidence.md").write_text(_evidence_md(skill, report, evidence), encoding="utf-8")
    (root / "references" / "verification-report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    for case in _eval_cases(requirements):
        (root / "evals" / f"{case['id']}.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    for name, data in (keyframes or {}).items():
        (root / "assets" / name).write_bytes(data)
    return root


def zip_dir(path: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(path.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(path.parent))
    return buffer.getvalue()


def _cite(evidence_ids: list[str], evidence: Mapping[str, Evidence]) -> str:
    cites = sorted({evidence[e].citation() for e in evidence_ids if e in evidence})
    return f" _(manual {', '.join(cites)})_" if cites else ""


def _skill_md(skill: SkillIR, report: VerificationReport, evidence: Mapping[str, Evidence]) -> str:
    lines = [
        "---",
        f"name: {skill.name}",
        f"description: {json.dumps(skill.description)}",
        "---",
        "",
        f"# {report.procedure}",
        "",
        skill.goal,
        "",
    ]
    if skill.preconditions:
        lines += ["## Before you start", ""]
        lines += [f"- {r.statement}{_cite(r.evidence_ids, evidence)}" for r in skill.preconditions]
        lines.append("")
    lines += ["## Procedure", ""]
    lines += [f"{i}. {s.instruction}{_cite(s.evidence_ids, evidence)}" for i, s in enumerate(skill.steps, start=1)]
    lines += ["", "## Rules that must hold", ""]
    for r in sorted(skill.rules, key=lambda r: ("critical", "major", "minor").index(r.severity)):
        lines.append(f"- **{r.severity.upper()}** {r.statement} — `{r.constraint}`{_cite(r.evidence_ids, evidence)}")
    deviations = [v for v in report.verdicts if v.status == Status.VIOLATION and v.review != "rejected"]
    if deviations:
        lines += ["", "## Deviations seen in practice", "", f"Observed in verification run {report.run_id}:", ""]
        lines += [f"- {v.statement.rstrip('.')}: {v.reason}" for v in deviations]
    unverified = [v for v in report.verdicts if v.status in (Status.UNVERIFIED, Status.INSUFFICIENT_EVIDENCE)]
    if unverified:
        lines += ["", "## Confirm separately", "", "These rules could not be confirmed from video and need other evidence:", ""]
        lines += [f"- {v.statement} — {v.needed_evidence or v.reason}" for v in unverified]
    lines += [
        "",
        "## When answering",
        "",
        "- Cite the manual location for every rule you state.",
        "- If the user describes a step that breaks a rule above, say which rule and what the manual requires.",
        "- Do not approve work as complete until every verification rule is satisfied.",
        "",
        "## References",
        "",
        "- `references/requirements.json` — compiled rules and event vocabulary",
        "- `references/evidence.md` — manual quotes behind each rule",
        "- `references/verification-report.json` — video verification results",
        "",
    ]
    return "\n".join(lines)


def _evidence_md(skill: SkillIR, report: VerificationReport, evidence: Mapping[str, Evidence]) -> str:
    lines = [f"# Evidence for {skill.name}", ""]
    for v in report.verdicts:
        lines += [f"## {v.rule_id} — {v.statement}", "", f"Constraint: `{v.constraint.signature()}` — result **{v.status}**: {v.reason}", ""]
        for eid in v.requirement_evidence_ids + v.observation_evidence_ids:
            item = evidence.get(eid)
            if item:
                source = "Manual" if item.source_type == "document" else "Video"
                lines.append(f"- {source} {item.citation()} (`{eid}`, sha256 {item.sha256[:12]}): {item.text or ''}")
        lines.append("")
    return "\n".join(lines)


def _eval_cases(requirements: RequirementSet) -> list[dict]:
    names = {e.label: e.description for e in requirements.events}
    cases = []
    for req in requirements.requirements:
        c = req.constraint
        if c.type == ConstraintType.MAX_INTERVAL:
            prompt = f"It took {c.seconds * 1.5:g} seconds between '{names[c.a]}' and '{names[c.b]}'. Is that acceptable?"
            must = [f"{c.seconds:g}"]
        elif c.type == ConstraintType.MUST_HAVE:
            prompt = f"I finished the procedure but skipped this: {names[c.event]}. Am I done?"
            must = []
        elif c.type in (ConstraintType.BEFORE, ConstraintType.PRECONDITION):
            prompt = f"Can I do '{names[c.b]}' before '{names[c.a]}'?"
            must = []
        elif c.type == ConstraintType.AFTER:
            prompt = f"Can I skip '{names[c.a]}' once '{names[c.b]}' is done?"
            must = []
        elif c.type == ConstraintType.MUST_NOT:
            prompt = f"Is it fine if I do this: {names[c.event]}?"
            must = []
        else:
            prompt = f"How many times do I need to do this: {names[c.event]}?"
            must = [str(c.min_count)]
        cases.append(
            {
                "id": f"{req.rule_id.lower()}-{c.type.lower()}",
                "rule_id": req.rule_id,
                "prompt": prompt,
                "expected": f"Flags or explains the rule: {req.statement}",
                "must_mention": must,
                "must_flag_problem": c.type != ConstraintType.COUNT,
            }
        )
    return cases
