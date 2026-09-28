"""Does the second look clear compliant recordings without hiding real violations? (run on the Spark)

Part A: the 12 cross-validation recordings. The low-confidence events of each held-out prediction are re-examined
with that fold's own reference images; we count how many true events are confirmed versus false ones, then how
many recordings the rules would clear before and after. Only the five rules that use the three-label vocabulary
the video backend is evaluated on are used.
Part B: the six edited recordings (compliant / missing cover / PSU before fans) through the deployed pipeline's
stored observations: verdict category before and after, against the known truth. The number that must stay zero
is violating recordings that end up cleared.

Usage (on the Spark, from ~/praxiproof, service running):
    uv run python deploy/eval/second_look_eval.py            # writes ~/praxiproof-data/eval/second_look.json
"""
import json
from pathlib import Path

from praxiproof.constraints.engine import evaluate
from praxiproof.demo import load_reference_requirements
from praxiproof.eval.metrics import temporal_iou
from praxiproof.eval.nvidia_sop import VOCABULARY, raw_video
from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.ir.requirement import RequirementSet
from praxiproof.ir.verification import VerificationReport
from praxiproof.llm import OllamaClient
from praxiproof.service import _result_summary
from praxiproof.store import Store
from praxiproof.verifier.aligner import llm_matcher
from praxiproof.video.ddm_vlm_adapter import DDMVLMBackend
from praxiproof.video.normalizer import RawSegment
from praxiproof.video.references import assign_references, load_references

HOME = Path.home()
DATA = HOME / "datasets/sop-server-fan/server_fan"
EVAL = HOME / "praxiproof-data/eval"
THRESHOLD = 0.5
LLM_MODEL, VLM_MODEL = "qwen3.6:35b-a3b-q8_0", "gemma4:31b"
llm = OllamaClient("http://127.0.0.1:11434", "30m")
matcher = llm_matcher(llm, LLM_MODEL)
backend = DDMVLMBackend(llm, VLM_MODEL, runner=None, second_look_below=THRESHOLD)


def look(path, references, vocabulary, event):
    segment = RawSegment(
        label=event["label"], description=event.get("description", ""), start=event["start"], end=event["end"],
        confidence=event["confidence"], uncertainty=event.get("uncertainty", 0.0),
    )
    return backend._second_look(path, segment, vocabulary, "server assembly", references)


def is_true_event(event, gold, used):
    best = None
    for i, g in enumerate(gold):
        if i in used or g["label"] != event["label"]:
            continue
        iou = temporal_iou(event["start"], event["end"], g["start"], g["end"])
        if iou >= 0.3 and (best is None or iou > best[0]):
            best = (iou, i)
    if best:
        used.add(best[1])
    return best is not None


def five_rules():
    demo = Path.home() / "praxiproof/demo"
    rs, *_ = load_reference_requirements(demo / "requirements" / "server-fan-psu-cover.json", demo)
    keep = [r for r in rs.requirements if "fan_connected" not in r.constraint.events() and r.constraint.type != "MUST_NOT"]
    return RequirementSet(source_id=rs.source_id, procedure=rs.procedure, events=[e for e in rs.events if e.label != "fan_connected"], requirements=keep)


def observation(name, events):
    ev = [ObservedEvent(event_id=f"O{i}", label=e["label"], start=e["start"], end=e["end"], confidence=e["confidence"]) for i, e in enumerate(events)]
    return Observation(source_id=name, duration=max([e.end for e in ev] + [1]), backend="ddm_vlm", events=ev, approximate=True, complete=True)


def part_a() -> dict:
    rules = five_rules()
    events_out, cleared = [], {"before": 0, "after": 0}
    recordings = {}
    for fold in range(1, 5):
        data = json.loads((EVAL / "cv" / f"fold{fold}.json").read_text())
        references = assign_references(load_references(HOME / f"praxiproof-data/references/cv_fold{fold}"), VOCABULARY, matcher)
        for name, v in data["videos"].items():
            used, after = set(), []
            for e in sorted(v["predicted"], key=lambda e: -e["confidence"]):
                truth = is_true_event(e, v["gold"], used)
                if e["confidence"] >= THRESHOLD:
                    after.append(e)
                    continue
                promoted = look(raw_video(DATA, name), references, VOCABULARY, e)
                events_out.append({"video": name, "label": e["label"], "is_true_event": truth, "votes": promoted.description.split("[")[-1].rstrip("]"),
                                   "confidence_after": promoted.confidence, "confirmed": promoted.confidence >= THRESHOLD})
                print(name, e["label"], "true" if truth else "false", "->", promoted.confidence, flush=True)
                after.append({**e, "confidence": promoted.confidence})
            recordings[name] = (v["predicted"], after)
    for name, (before, after) in recordings.items():
        cleared["before"] += all(x.status.value == "PASS" for x in evaluate(rules, observation(name, before), THRESHOLD))
        cleared["after"] += all(x.status.value == "PASS" for x in evaluate(rules, observation(name, after), THRESHOLD))
    true_ev = [e for e in events_out if e["is_true_event"]]
    false_ev = [e for e in events_out if not e["is_true_event"]]
    return {
        "recordings": len(recordings),
        "weak_events": len(events_out),
        "true_events_confirmed": f"{sum(e['confirmed'] for e in true_ev)}/{len(true_ev)}",
        "false_events_confirmed": f"{sum(e['confirmed'] for e in false_ev)}/{len(false_ev)}",
        "recordings_cleared_before": cleared["before"],
        "recordings_cleared_after": cleared["after"],
        "events": events_out,
    }


def part_b() -> dict:
    store = Store(HOME / "praxiproof-data" / "praxiproof.db")
    baseline = json.loads((EVAL / "baseline_vs_praxiproof.json").read_text())
    references_dir = HOME / "praxiproof-data/references/server_fan"
    rows = []
    for video, entry in baseline["videos"].items():
        run = store.get("runs", store.get("pipelines", entry["praxiproof"]["pipeline"])["run_id"])
        requirements = RequirementSet.model_validate(store.get("manuals", run["manual_id"])["requirement_set"])
        obs = Observation.model_validate(run["observation"])
        references = assign_references(load_references(references_dir), requirements.events, matcher)
        path = Path(store.get("videos", run["video_id"])["path"])

        def category(o: Observation) -> str:
            verdicts = evaluate(requirements, o, THRESHOLD)
            report = VerificationReport(run_id="x", manual_id="x", video_id=None, procedure=requirements.procedure, verdicts=verdicts)
            return _result_summary(report)["result"]

        new_events, promoted = [], 0
        for e in obs.events:
            if e.confidence < THRESHOLD:
                out = look(path, references, requirements.events, {"label": e.label, "description": e.description, "start": e.start, "end": e.end,
                                                                   "confidence": e.confidence, "uncertainty": e.time_uncertainty})
                promoted += out.confidence >= THRESHOLD
                e = e.model_copy(update={"confidence": out.confidence, "description": out.description})
            new_events.append(e)
        after = category(obs.model_copy(update={"events": new_events}))
        rows.append({"video": video, "truth": entry["truth"], "before": category(obs), "after": after, "weak_events": sum(x.confidence < THRESHOLD for x in obs.events), "promoted": promoted})
        print(video, entry["truth"], "|", rows[-1]["before"], "->", after, flush=True)
    violating = [r for r in rows if r["truth"] != "Compliant"]
    return {
        "rows": rows,
        "violating_recordings_wrongly_cleared_before": sum(r["before"] == "PASS" for r in violating),
        "violating_recordings_wrongly_cleared_after": sum(r["after"] == "PASS" for r in violating),
        "compliant_cleared_before": sum(r["before"] == "PASS" for r in rows if r["truth"] == "Compliant"),
        "compliant_cleared_after": sum(r["after"] == "PASS" for r in rows if r["truth"] == "Compliant"),
        "verdict_category_matches_truth_before": sum(r["before"] == {"Compliant": "PASS"}.get(r["truth"], r["truth"]) for r in rows),
        "verdict_category_matches_truth_after": sum(r["after"] == {"Compliant": "PASS"}.get(r["truth"], r["truth"]) for r in rows),
    }


if __name__ == "__main__":
    result = {"threshold": THRESHOLD, "vlm": VLM_MODEL, "cross_validation_recordings": part_a(), "edited_recordings": part_b()}
    (EVAL / "second_look.json").write_text(json.dumps(result, indent=2))
    summary = {k: v for k, v in result["cross_validation_recordings"].items() if k != "events"}
    print(json.dumps({"cross_validation_recordings": summary, "edited_recordings": {k: v for k, v in result["edited_recordings"].items() if k != "rows"}}, indent=2))
