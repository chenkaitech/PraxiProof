"""Manual<->video alignment check on IKEA Assembly in the Wild (Zhang et al., CVPR 2023 workshop;
github.com/DavidZhang73/IKEAAssemblyInTheWildDataset), a second out-of-domain dataset distinct from
Assembly101: real IKEA products, real customer-facing manuals, real (not staged) YouTube assembly
videos, with human-annotated ground-truth step timing.

Why this needed a different approach than the normal compile_requirements() pipeline: IKEA manuals
are near-pure diagrams (see data/ikea-asw-expansion/VESKEN_50453881/page-2.png) -- the text extractor
pulls almost nothing usable ("L", "R", part codes, no verbs). Compiling rules from extracted text
would compile from noise. Building rules by reading the diagrams with vision is a real capability
this project does not have yet (see docs/report limitations). Instead, this script builds the
RequirementSet directly from a human read of the manual (this file's VESKEN_EVENTS/REQUIREMENTS
below), and uses the IAW dataset's own human-annotated step_annotations (data/ikea-asw-expansion/
VESKEN_50453881/ground_truth.json) as the timing ground truth to compare the pipeline's output
against -- not as an oracle answer key handed to the compiler, only as a scoring reference.

VESKEN (a small IKEA storage trolley) has 3 manual steps, each performed twice (left+right / two
wheel units), assembled in a fixed order:
  1. caster wheels clicked onto 4 leg pieces           -> event: wheels_attached_to_legs (count 2)
  2. the 4 leg+wheel units clicked onto the tray base   -> event: legs_attached_to_tray   (count 2)
  3. the 4 vertical posts clicked into the leg units    -> event: posts_inserted          (count 2)
This is a genuine (not staged) assembly video, so the expected verdict on all rules is PASS; the
"violation type" ground truth for this item is "none" -- see the module docstring caveat on scope.

Usage (on the Spark): uv run python deploy/eval/ikea_alignment_eval.py [output.json]
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
PROCEDURE = "VESKEN Trolley Assembly"

VESKEN_EVENTS = [
    EventDef(label="wheels_attached_to_legs", description="A caster wheel unit clicked onto a vertical leg piece (see manual page 2, step 1)"),
    EventDef(label="legs_attached_to_tray", description="A leg+wheel unit clicked onto a corner of the tray base (see manual page 3, step 2)"),
    EventDef(label="posts_inserted", description="A vertical post clicked into a leg unit already attached to the tray (see manual page 3, step 3)"),
]
VESKEN_REQUIREMENTS = [
    Requirement(rule_id="R-001", statement="At least 2 wheel units must be attached to leg pieces", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="COUNT", event="wheels_attached_to_legs", min_count=2)),
    Requirement(rule_id="R-002", statement="At least 2 leg units must be attached to the tray", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="COUNT", event="legs_attached_to_tray", min_count=2)),
    Requirement(rule_id="R-003", statement="At least 2 posts must be inserted", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="COUNT", event="posts_inserted", min_count=2)),
    Requirement(rule_id="R-004", statement="Wheels must be attached to legs before those legs are attached to the tray", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="BEFORE", a="wheels_attached_to_legs", b="legs_attached_to_tray")),
    Requirement(rule_id="R-005", statement="Legs must be attached to the tray before the posts are inserted", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="BEFORE", a="legs_attached_to_tray", b="posts_inserted")),
]

# Ground-truth step timing (IAW human annotation) mapped onto our 3 coarser events: which of the
# dataset's 7 fine-grained `action` indices belongs to which of our events, for scoring only.
ACTION_TO_EVENT = {0: None, 1: "wheels_attached_to_legs", 2: "wheels_attached_to_legs",
                   3: "legs_attached_to_tray", 4: "legs_attached_to_tray",
                   5: "posts_inserted", 6: "posts_inserted"}


def gold_events() -> list[dict]:
    gt = json.loads((DATA_DIR / "VESKEN_50453881" / "ground_truth.json").read_text())
    out = []
    for a in gt["step_annotations"]:
        label = ACTION_TO_EVENT.get(a["action"])
        if label:
            out.append({"label": label, "start": a["start"], "end": a["end"]})
    return out


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "docs/eval/ikea_alignment.json"
    settings = load_overrides(get_settings())
    llm = build_llm(settings)
    vlm = build_vlm(settings, llm)
    backend = LocalVLMBackend(vlm, settings.vlm_model)

    requirements = RequirementSet(source_id="IKEA-VESKEN", procedure=PROCEDURE, events=VESKEN_EVENTS, requirements=VESKEN_REQUIREMENTS, compiler_model="reference")
    video_path = DATA_DIR / "VESKEN_50453881" / "video.mp4"

    started = time.time()
    observation, _ = backend.observe(video_path, "VESKEN", VESKEN_EVENTS, PROCEDURE)
    elapsed = round(time.time() - started)

    verdicts = evaluate(requirements, observation, settings.min_confidence)
    detected = [{"label": e.label, "start": round(e.start, 1), "end": round(e.end, 1), "confidence": e.confidence} for e in observation.events]
    gold = gold_events()
    gold_ev = [ObservedEvent(event_id=f"G-{i}", label=g["label"], start=g["start"], end=g["end"], confidence=1.0) for i, g in enumerate(gold)]
    pred_ev = [ObservedEvent(event_id=f"P-{i}", label=e["label"], start=e["start"], end=e["end"], confidence=e["confidence"]) for i, e in enumerate(detected)]
    detection_metrics = event_detection(pred_ev, gold_ev)

    report = {
        "item": "VESKEN_50453881",
        "video_seconds": 55,
        "pipeline_seconds": elapsed,
        "manual_events": [e.label for e in VESKEN_EVENTS],
        "detected_events": detected,
        "gold_events": gold,
        "detection_metrics": detection_metrics,
        "verdicts": [{"rule_id": v.rule_id, "status": v.status.value, "reason": v.reason} for v in verdicts],
        "expected_verdicts": {"R-001": "PASS", "R-002": "PASS", "R-003": "PASS", "R-004": "PASS", "R-005": "PASS"},
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
