"""Third IKEA-ASW alignment check (see ikea_alignment_eval.py for the method note). HOLMSUND (a
three-seat sofa bed) has a 40-page manual; this particular YouTube video is a partial/highlights
clip covering only 7 of the 41 manual steps, non-contiguously (steps 17, then 33-40) -- confirmed by
cross-referencing step_annotations against manual_annotation_list, not assumed.

Two coarse phases were hand-verified by viewing the manual pages:
  1. frame_leg_attached: driving 4 leg screws into the frame base by hand (manual step 17, page 19).
     One video action (index 17) covers this.
  2. cushion_cover_fitted: pulling the fabric mattress cover over the frame and closing the zipper
     (manual steps 32-40, pages 31-37 -- viewed page 31, which shows exactly this). Six video actions
     (33, 34, 36, 38, 39, 40) fall in this range and are all treated as the same coarse event, since
     they were not individually distinguished by viewing every one of pages 32-37.

Usage (on the Spark): uv run python deploy/eval/ikea_holmsund_eval.py [output.json]
"""
import json
import sys
import time
from pathlib import Path

from praxiproof.config import get_settings, load_overrides
from praxiproof.constraints.engine import evaluate
from praxiproof.constraints.schema import Constraint
from praxiproof.eval.metrics import event_detection
from praxiproof.ir.observation import ObservedEvent
from praxiproof.ir.requirement import EventDef, Requirement, RequirementSet
from praxiproof.llm import build_llm, build_vlm
from praxiproof.video.local_vlm_adapter import LocalVLMBackend

HERE = Path(__file__).parent
DATA_DIR = HERE.parent.parent / "data" / "ikea-asw-expansion"
PROCEDURE = "HOLMSUND Sofa Bed Assembly (partial highlights clip: leg attachment + cushion fitting only)"

EVENTS = [
    EventDef(label="frame_leg_attached", description="A leg screw driven by hand into the underside of the sofa bed frame base (manual page 19, step 17)"),
    EventDef(label="cushion_cover_fitted", description="The fabric mattress/cushion cover being pulled over the frame and its zipper closed (manual pages 31-37, steps 32-40)"),
]
REQUIREMENTS = [
    Requirement(rule_id="R-001", statement="At least one frame leg screw must be installed", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="MUST_HAVE", event="frame_leg_attached")),
    Requirement(rule_id="R-002", statement="The cushion cover must be fitted", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="COUNT", event="cushion_cover_fitted", min_count=1)),
    Requirement(rule_id="R-003", statement="Leg screws must be installed before the cushion cover is fitted", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="BEFORE", a="frame_leg_attached", b="cushion_cover_fitted")),
]

ACTION_TO_EVENT = {17: "frame_leg_attached", 33: "cushion_cover_fitted", 34: "cushion_cover_fitted",
                   36: "cushion_cover_fitted", 38: "cushion_cover_fitted", 39: "cushion_cover_fitted", 40: "cushion_cover_fitted"}


def gold_events() -> list[dict]:
    gt = json.loads((DATA_DIR / "HOLMSUND_s69240762" / "ground_truth.json").read_text())
    return [{"label": ACTION_TO_EVENT[a["action"]], "start": a["start"], "end": a["end"]} for a in gt["step_annotations"] if a["action"] in ACTION_TO_EVENT]


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "docs/eval/ikea_holmsund.json"
    settings = load_overrides(get_settings())
    llm = build_llm(settings)
    vlm = build_vlm(settings, llm)
    backend = LocalVLMBackend(vlm, settings.vlm_model)

    requirements = RequirementSet(source_id="IKEA-HOLMSUND", procedure=PROCEDURE, events=EVENTS, requirements=REQUIREMENTS, compiler_model="reference")
    video_path = DATA_DIR / "HOLMSUND_s69240762" / "video.mp4"

    started = time.time()
    observation, _ = backend.observe(video_path, "HOLMSUND", EVENTS, PROCEDURE)
    elapsed = round(time.time() - started)

    verdicts = evaluate(requirements, observation, settings.min_confidence)
    detected = [{"label": e.label, "start": round(e.start, 1), "end": round(e.end, 1), "confidence": e.confidence} for e in observation.events]
    gold = gold_events()
    gold_ev = [ObservedEvent(event_id=f"G-{i}", label=g["label"], start=g["start"], end=g["end"], confidence=1.0) for i, g in enumerate(gold)]
    pred_ev = [ObservedEvent(event_id=f"P-{i}", label=e["label"], start=e["start"], end=e["end"], confidence=e["confidence"]) for i, e in enumerate(detected)]
    detection_metrics = event_detection(pred_ev, gold_ev)

    report = {
        "item": "HOLMSUND_s69240762",
        "scope_note": "partial/highlights video covering only manual steps 17 and 32-40 of 41 total; not a full assembly",
        "video_seconds": 60,
        "pipeline_seconds": elapsed,
        "manual_events": [e.label for e in EVENTS],
        "detected_events": detected,
        "gold_events": gold,
        "detection_metrics": detection_metrics,
        "verdicts": [{"rule_id": v.rule_id, "status": v.status.value, "reason": v.reason} for v in verdicts],
        "expected_verdicts": {"R-001": "PASS", "R-002": "PASS", "R-003": "PASS"},
        "all_pass": all(v.status.value == "PASS" for v in verdicts),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"observed in {elapsed}s, detected {len(detected)} events")
    for v in verdicts:
        print(f"  {v.rule_id}: {v.status.value} -- {v.reason}")
    print(f"detection metrics: {detection_metrics}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
