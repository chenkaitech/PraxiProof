"""Score deploy/eval/generalization_eval.py's predictions with the real rule engine.

The raw script (GPU-bound, run once on the Spark) only saves the predicted events. This module defines the same
10 rules the manual compiled to (recorded in generalization_eval.py's log; compilation is not deterministic across
runs, so they are fixed here rather than re-derived) and asks `praxiproof.constraints.engine.evaluate` what
PraxiProof would actually conclude about each recording -- the same code path a real run uses, not a bespoke scorer.

Usage: python -m praxiproof.eval.generalization_summary <generalization.json> <output.json>
"""
import json
import sys
from pathlib import Path

from praxiproof.constraints.engine import evaluate
from praxiproof.constraints.schema import Constraint
from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.ir.requirement import EventDef, Requirement, RequirementSet

EVENTS = ["screws_removed", "toy_disassembled", "parts_set_aside", "toy_reassembled", "toy_held_together_confirmed"]

# From the compile step's own log: MUST_HAVE for every event, plus every BEFORE/AFTER order the manual implies.
RULES = [
    ("R-001", "MUST_HAVE", {"event": "screws_removed"}),
    ("R-002", "MUST_HAVE", {"event": "toy_disassembled"}),
    ("R-003", "MUST_HAVE", {"event": "parts_set_aside"}),
    ("R-004", "MUST_HAVE", {"event": "toy_reassembled"}),
    ("R-005", "MUST_HAVE", {"event": "toy_held_together_confirmed"}),
    ("R-006", "BEFORE", {"a": "toy_disassembled", "b": "toy_reassembled"}),
    ("R-007", "AFTER", {"a": "toy_held_together_confirmed", "b": "toy_reassembled"}),
    ("R-008", "BEFORE", {"a": "parts_set_aside", "b": "toy_reassembled"}),
    ("R-009", "BEFORE", {"a": "toy_disassembled", "b": "parts_set_aside"}),
    ("R-010", "BEFORE", {"a": "screws_removed", "b": "toy_disassembled"}),
]


def build_requirements() -> RequirementSet:
    events = [EventDef(label=label, description=label) for label in EVENTS]
    requirements = [Requirement(rule_id=rid, statement=rid, constraint=Constraint(type=kind, **fields), category="procedure", severity="major", evidence_ids=[]) for rid, kind, fields in RULES]
    return RequirementSet(source_id="GENERALIZATION", procedure="Toy Front Loader Teardown and Rebuild", events=events, requirements=requirements)


def score(report: dict, min_confidence: float = 0.5) -> dict:
    rs = build_requirements()
    out = {"rule_count": len(RULES), "videos": {}}
    for name, video in report["videos"].items():
        events = [ObservedEvent(event_id=f"E{i}", label=e["label"], start=e["start"], end=e["end"], confidence=e["confidence"]) for i, e in enumerate(video["predicted"])]
        observation = Observation(source_id=name, duration=max((e.end for e in events), default=1.0), backend="local_vlm", events=events, approximate=True, complete=True)
        verdicts = evaluate(rs, observation, min_confidence)
        counts: dict[str, int] = {}
        for v in verdicts:
            counts[v.status.value] = counts.get(v.status.value, 0) + 1
        out["videos"][name] = {
            "counts": counts,
            "verdicts": [{"rule_id": v.rule_id, "status": v.status.value, "reason_code": v.reason_code} for v in verdicts],
        }
    return out


if __name__ == "__main__":
    result = score(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({n: v["counts"] for n, v in result["videos"].items()}, indent=2))
