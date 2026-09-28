"""Fixed-rule, fixed-annotation-mapping evaluation on the 8 newly added held-out Assembly101 sessions
(deploy/eval/generalization_eval.py's original 3-session check tuned prompts/reference selection on
this dataset; these 8 are additional held-out toys/participants never touched during that work, see
data/assembly101-expansion/sessions.json).

"Fixed" means: one event vocabulary and one rule, identical across all 8 sessions and all 8 different
toys -- no per-session or per-toy customization, unlike the IKEA-ASW checks (ikea_*_eval.py) which
needed hand-authored rules per furniture item since IKEA manuals have no reusable text. Assembly101's
coarse action labels are a closed 11-verb x 61-noun vocabulary (annotations/coarse-annotations/
actions.csv), so a single verb-based mapping generalizes across every toy without per-item work:

  assembly_action:     verb in {attach, screw, attempt to attach, attempt to screw}
  disassembly_action:  verb in {detach, remove, unscrew, attempt to detach}
  (excluded from both: inspect, position, demonstrate -- neither assembling nor disassembling)

Ground truth: the real coarse_labels/{assembly,disassembly}_{session}.txt files (frame_start,
frame_end, action_cls), frame numbers converted to seconds at 30fps per the dataset's own README
("frame numbers in all annotations are provided after extracting at 30fps", even though the source
video is 60fps -- confirmed by checking a video file's native fps directly, not assumed).

Fixed rule: BEFORE(disassembly_action, assembly_action) -- every Assembly101 "action_both" recording
is one continuous take of a participant disassembling then reassembling the same toy, so this should
hold for all 8, modulo real assembly errors: Assembly101 explicitly includes natural mistakes and
corrections (e.g. "unscrew" segments appearing inside the reassembly half of the timeline are a
participant undoing their own error, not an annotation error -- kept as-is, not filtered out).

Uses local_vlm (not ddm_vlm): DDM-Net is fine-tuned for the DGX H100 fan chassis, so running it here
would measure a known domain mismatch, not generalization (see generalization_eval.py).

Usage (on the Spark, ~5-10 min per session depending on length):
  uv run python deploy/eval/assembly101_expansion_eval.py [output.json]
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
DATA_DIR = HERE.parent.parent / "data" / "assembly101-expansion"
PROCEDURE = "Toy vehicle disassembly and reassembly (Assembly101, fixed cross-toy rule)"
FPS = 30.0  # annotation frame numbers are indexed at 30fps regardless of the source video's native fps

ASSEMBLY_VERBS = {"attach", "screw", "attempt to attach", "attempt to screw"}
DISASSEMBLY_VERBS = {"detach", "remove", "unscrew", "attempt to detach"}

EVENTS = [
    EventDef(label="disassembly_action", description="A part being removed, detached, or unscrewed from the toy vehicle"),
    EventDef(label="assembly_action", description="A part being attached, inserted, or screwed onto the toy vehicle"),
]
REQUIREMENTS = [
    Requirement(rule_id="R-001", statement="The toy must be disassembled at some point", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="MUST_HAVE", event="disassembly_action")),
    Requirement(rule_id="R-002", statement="The toy must be reassembled at some point", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="MUST_HAVE", event="assembly_action")),
    Requirement(rule_id="R-003", statement="Disassembly must occur before reassembly", category="procedure", severity="major", observable=True,
                constraint=Constraint(type="BEFORE", a="disassembly_action", b="assembly_action")),
]


def classify(action_cls: str) -> str | None:
    """Classify a line by its own verb, independent of which file (assembly/disassembly) it came
    from: Assembly101 files are named for which HALF of the recording they cover, not a guarantee
    that every line in the "assembly" half is itself an assembly-direction action -- a participant
    correcting their own mistake shows up as e.g. "unscrew chassis" inside assembly_X.txt."""
    text = action_cls.strip()
    if any(text.startswith(v) for v in ASSEMBLY_VERBS):
        return "assembly_action"
    if any(text.startswith(v) for v in DISASSEMBLY_VERBS):
        return "disassembly_action"
    return None


def load_gold(session: str) -> list[dict]:
    events = []
    for kind in ("disassembly", "assembly"):
        path = DATA_DIR / "annotations" / f"{session}_{kind}.txt"
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            start_f, end_f, action_cls = line.split("\t")[:3]
            label = classify(action_cls)
            if label:
                events.append({"label": label, "start": int(start_f) / FPS, "end": int(end_f) / FPS})
    return sorted(events, key=lambda e: e["start"])


def run_session(backend: LocalVLMBackend, requirements: RequirementSet, session: str) -> dict:
    video_path = DATA_DIR / "videos" / f"{session}_C10095_rgb.mp4"
    started = time.time()
    observation, _ = backend.observe(video_path, session, EVENTS, PROCEDURE)
    elapsed = round(time.time() - started)

    verdicts = evaluate(requirements, observation, 0.5)
    detected = [{"label": e.label, "start": round(e.start, 1), "end": round(e.end, 1), "confidence": e.confidence} for e in observation.events]
    gold = load_gold(session)
    gold_ev = [ObservedEvent(event_id=f"G-{i}", label=g["label"], start=g["start"], end=g["end"], confidence=1.0) for i, g in enumerate(gold)]
    pred_ev = [ObservedEvent(event_id=f"P-{i}", label=e["label"], start=e["start"], end=e["end"], confidence=e["confidence"]) for i, e in enumerate(detected)]

    return {
        "session": session,
        "pipeline_seconds": elapsed,
        "gold_event_count": len(gold),
        "detected_event_count": len(detected),
        "detected_events": detected,
        "detection_metrics": event_detection(pred_ev, gold_ev),
        "verdicts": [{"rule_id": v.rule_id, "status": v.status.value, "reason": v.reason} for v in verdicts],
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "docs/eval/assembly101_expansion.json"
    settings = load_overrides(get_settings())
    llm = build_llm(settings)
    vlm = build_vlm(settings, llm)
    backend = LocalVLMBackend(vlm, settings.vlm_model)
    requirements = RequirementSet(source_id="ASSEMBLY101-EXPANSION", procedure=PROCEDURE, events=EVENTS, requirements=REQUIREMENTS, compiler_model="reference")

    sessions = sorted(json.loads((DATA_DIR / "sessions.json").read_text()).keys())
    results = []
    for i, session in enumerate(sessions, 1):
        print(f"=== [{i}/{len(sessions)}] {session} ===", flush=True)
        try:
            r = run_session(backend, requirements, session)
        except Exception as exc:  # noqa: BLE001 - a batch eval should record a failure, not crash the whole run
            print(f"  FAILED: {exc}")
            r = {"session": session, "error": str(exc)[:300]}
        results.append(r)
        if "verdicts" in r:
            print(f"  {r['pipeline_seconds']}s, {r['detected_event_count']} detected vs {r['gold_event_count']} gold, metrics={r['detection_metrics']}")
            for v in r["verdicts"]:
                print(f"    {v['rule_id']}: {v['status']}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"fixed_rule": [req.statement for req in REQUIREMENTS], "results": results}, indent=2))

    ok = [r for r in results if "verdicts" in r]
    r003_pass = sum(1 for r in ok if any(v["rule_id"] == "R-003" and v["status"] == "PASS" for v in r["verdicts"]))
    print(f"\n{len(ok)}/{len(sessions)} sessions completed; R-003 (order) PASS on {r003_pass}/{len(ok)}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
