"""Out-of-domain generalization check: a public dataset the pipeline was never tuned on.

All 12 fan-installation recordings used everywhere else in this project come from the same NVIDIA
sample dataset, the same room and the same chassis (see the README's "known limitations"). This
script instead compiles a manual for an unrelated task (taking a toy vehicle apart and rebuilding
it) and runs it against three real recordings from Assembly101 (Sener et al., CVPR 2022; sample
re-hosted at huggingface.co/datasets/pablovela5620/Assembly101-Sample, CC-BY-NC-4.0) -- a different
dataset, different physical scene, different task, different participants, never seen during
DDM-Net fine-tuning or prompt/reference tuning.

DDM-Net (the boundary detector) is fine-tuned specifically for the server-fan chassis, so running
it here would not measure generalization, it would measure a mismatch we already know exists. This
uses the `local_vlm` backend instead: plain sliding-window VLM classification with no fine-tuned
component, which is the part of the stack that a from-scratch procedure has to rely on.

Ground truth for `session2` was built by hand (sampling a frame every 20s and watching the
disassembly/reassembly happen), so it is accurate to roughly +/-10s, not frame-accurate like the
project's other eval sets; `session1` and `session3` have no ground truth and are reported only as
the pipeline's raw output, to see whether the same two-phase structure shows up on different toys,
different participants and different tools.

Usage (on the Spark): uv run python deploy/eval/generalization_eval.py [output.json]
"""
import json
import sys
import time
from pathlib import Path

from praxiproof.config import get_settings, load_overrides
from praxiproof.constraints.compiler import compile_requirements
from praxiproof.document.extract import extract
from praxiproof.eval.metrics import event_detection
from praxiproof.ir.observation import ObservedEvent
from praxiproof.llm import build_llm, build_vlm
from praxiproof.video.local_vlm_adapter import LocalVLMBackend

HERE = Path(__file__).parent
MANUAL = HERE / "generalization" / "manual-toy-loader.md"
VIDEOS = Path.home() / "datasets/assembly101-sample"
PROCEDURE = "Toy Front Loader Teardown and Rebuild"

# Hand-built from watching session2 at a 20s sampling rate (see the module docstring for the caveat).
SESSION2_GOLD_PHASES = [("apart", 0.0, 190.0), ("rebuil", 190.0, 287.9)]


def pick_label(events: list, *keywords: str) -> str | None:
    for event in events:
        text = f"{event.label} {event.description}".lower()
        if any(k in text for k in keywords):
            return event.label
    return None


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "praxiproof-data/eval/generalization.json"
    settings = load_overrides(get_settings())
    llm = build_llm(settings)
    vlm = build_vlm(settings, llm)
    backend = LocalVLMBackend(vlm, settings.vlm_model)

    doc = extract(MANUAL, source_id="GENERALIZATION")
    result = compile_requirements(doc, llm, settings.llm_model, PROCEDURE)
    vocabulary = result.requirement_set.events
    rules = [{"rule_id": r.rule_id, "statement": r.statement, "constraint": r.constraint.signature()} for r in result.requirement_set.requirements]
    print(f"compiled {len(vocabulary)} event(s), {len(rules)} rule(s): {[e.label for e in vocabulary]}")
    for r in rules:
        print(" ", r["rule_id"], r["constraint"], "-", r["statement"])

    apart_label = pick_label(vocabulary, "apart", "disassemb", "remov")
    rebuilt_label = pick_label(vocabulary, "rebuil", "reassemb", "together")
    if not apart_label or not rebuilt_label or apart_label == rebuilt_label:
        print(f"WARNING: could not confidently map compiled events to the two phases (apart={apart_label!r}, rebuilt={rebuilt_label!r})")

    videos = sorted(VIDEOS.glob("session*.mp4"))
    report: dict = {"compiled": {"events": [e.label for e in vocabulary], "rules": rules}, "videos": {}}
    for path in videos:
        started = time.time()
        observation, _ = backend.observe(path, path.stem, vocabulary, PROCEDURE)
        seconds = round(time.time() - started)
        events = [{"label": e.label, "start": round(e.start, 1), "end": round(e.end, 1), "confidence": e.confidence} for e in observation.events]
        entry = {"seconds": seconds, "predicted": events}
        if path.stem == "session2_9012-c07c_C10095" and apart_label and rebuilt_label:
            keyword_to_label = {"apart": apart_label, "rebuil": rebuilt_label}
            gold = [
                ObservedEvent(event_id=f"G{i}", label=keyword_to_label[kw], start=s, end=e, confidence=1.0)
                for i, (kw, s, e) in enumerate(SESSION2_GOLD_PHASES)
            ]
            predicted = [ObservedEvent(event_id=f"P{i}", **{k: v for k, v in ev.items()}) for i, ev in enumerate(events)]
            entry["gold"] = [{"label": g.label, "start": g.start, "end": g.end} for g in gold]
            entry["scored_against_gold"] = event_detection(predicted, gold, iou_threshold=0.2)
        report["videos"][path.stem] = entry
        print(path.stem, seconds, "s ->", events, entry.get("scored_against_gold", ""))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
