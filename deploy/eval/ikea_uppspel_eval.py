"""Second IKEA-ASW alignment check (see ikea_alignment_eval.py for the full method note). UPPSPEL
(a drawer unit on castors) has a 24-page manual and 31 fine-grained video actions -- too many pages
to hand-verify in full within this pass, so this test is deliberately scoped down to the 2 event
types actually confirmed by viewing the manual images (page-4.png, page-6.png):
  1. hardware_installed_on_panel: 16 dowel/cam screws driven into the two side panels (manual step 1,
     page 4) -- one video action (index 1) covers this.
  2. rails_installed_on_panel: the two drawer slide rails screwed onto the panels (manual step 3,
     page 6, explicitly labelled "2x") -- video actions 3 and 4 cover this.
The remaining ~27 video actions (pages 5, 7-22) were not viewed and are excluded from both the rule
set and the gold comparison -- this is a partial check of the first few manual steps, not the whole
24-page assembly, and is reported as such rather than silently treated as complete.

Usage (on the Spark): uv run python deploy/eval/ikea_uppspel_eval.py [output.json]
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
PROCEDURE = "UPPSPEL Drawer Unit Assembly (partial: manual steps 1 and 3 only)"

EVENTS = [
    EventDef(label="hardware_installed_on_panel", description="Small dowel/cam screws driven into pre-drilled holes on a flat panel using a screwdriver (manual page 4, step 1)"),
    EventDef(label="rails_installed_on_panel", description="A metal drawer slide rail screwed flat onto a panel (manual page 6, step 3)"),
]
REQUIREMENTS = [
    Requirement(rule_id="R-001", statement="Hardware must be installed on at least one panel", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="MUST_HAVE", event="hardware_installed_on_panel")),
    Requirement(rule_id="R-002", statement="Both drawer slide rails must be installed", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="COUNT", event="rails_installed_on_panel", min_count=2)),
    Requirement(rule_id="R-003", statement="Panel hardware must be installed before the rails are attached", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="BEFORE", a="hardware_installed_on_panel", b="rails_installed_on_panel")),
]

# action index -> our coarse event label, for the 2 actions covered; None = out of scope for this pass.
ACTION_TO_EVENT = {1: "hardware_installed_on_panel", 3: "rails_installed_on_panel", 4: "rails_installed_on_panel"}


def gold_events() -> list[dict]:
    gt = json.loads((DATA_DIR / "UPPSPEL_70499840" / "ground_truth.json").read_text())
    return [{"label": ACTION_TO_EVENT[a["action"]], "start": a["start"], "end": a["end"]} for a in gt["step_annotations"] if a["action"] in ACTION_TO_EVENT]


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "docs/eval/ikea_uppspel.json"
    settings = load_overrides(get_settings())
    llm = build_llm(settings)
    vlm = build_vlm(settings, llm)
    backend = LocalVLMBackend(vlm, settings.vlm_model)

    requirements = RequirementSet(source_id="IKEA-UPPSPEL", procedure=PROCEDURE, events=EVENTS, requirements=REQUIREMENTS, compiler_model="reference")
    video_path = DATA_DIR / "UPPSPEL_70499840" / "video.mp4"

    started = time.time()
    observation, _ = backend.observe(video_path, "UPPSPEL", EVENTS, PROCEDURE)
    elapsed = round(time.time() - started)

    verdicts = evaluate(requirements, observation, settings.min_confidence)
    detected = [{"label": e.label, "start": round(e.start, 1), "end": round(e.end, 1), "confidence": e.confidence} for e in observation.events]
    gold = gold_events()
    gold_ev = [ObservedEvent(event_id=f"G-{i}", label=g["label"], start=g["start"], end=g["end"], confidence=1.0) for i, g in enumerate(gold)]
    pred_ev = [ObservedEvent(event_id=f"P-{i}", label=e["label"], start=e["start"], end=e["end"], confidence=e["confidence"]) for i, e in enumerate(detected)]
    detection_metrics = event_detection(pred_ev, gold_ev)

    report = {
        "item": "UPPSPEL_70499840",
        "scope_note": "partial: only manual steps 1 (hardware) and 3 (rails) were hand-verified; pages 5, 7-22 excluded",
        "video_seconds": 56,
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
