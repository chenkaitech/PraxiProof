from praxiproof.constraints.engine import evaluate
from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.ir.requirement import EventDef
from praxiproof.ir.verification import VerificationReport
from praxiproof.service import observation_with_evidence
from praxiproof.verifier.aligner import align, llm_matcher
from praxiproof.verifier.evidence import traceability
from tests.conftest import FakeLLM

VOCAB = [
    EventDef(label="fan_removed", description="Failed fan module pulled fully out of its bay"),
    EventDef(label="fan_inserted", description="New fan module pushed fully into the empty fan bay"),
]


def _observation(*labels: tuple[str, str]) -> Observation:
    return Observation(
        source_id="V",
        duration=60,
        backend="test",
        events=[
            ObservedEvent(event_id=f"O-{i}", label=label, description=desc, start=i * 10, end=i * 10 + 3, confidence=0.9)
            for i, (label, desc) in enumerate(labels, start=1)
        ],
    )


def test_exact_and_model_alignment():
    def handler(model, messages, schema, images):
        observed = schema["properties"]["matches"]["items"]["properties"]["observed"]["enum"]
        steps = schema["properties"]["matches"]["items"]["properties"]["steps"]["items"]["enum"]
        assert observed == ["old_fan_pulled_out", "coffee_break", "fan_swapped"]
        assert steps == ["fan_removed", "fan_inserted"]
        return {
            "matches": [
                {"observed": "old_fan_pulled_out", "steps": ["fan_removed"]},
                {"observed": "coffee_break", "steps": []},
                {"observed": "fan_swapped", "steps": ["fan_removed", "fan_inserted"]},
            ]
        }

    observation = _observation(
        ("fan_removed", "fan out"),
        ("old_fan_pulled_out", "failed fan module pulled out of its bay"),
        ("coffee_break", "technician drinks coffee"),
        ("old_fan_pulled_out", "second pull"),
        ("fan_swapped", "old fan pulled and new fan pushed in"),
    )
    fake = FakeLLM(json_handler=handler)
    aligned, records = align(observation, VOCAB, llm_matcher(fake, "m"))
    assert [r["method"] for r in records] == ["exact", "model", "unmatched", "model", "model"]
    assert records[4]["aligned_labels"] == ["fan_removed", "fan_inserted"]
    assert [(e.event_id, e.label) for e in aligned.events] == [
        ("O-1", "fan_removed"), ("O-2", "fan_removed"), ("O-3", "coffee_break"), ("O-4", "fan_removed"),
        ("O-5", "fan_removed"), ("O-5.2", "fan_inserted"),
    ]
    assert aligned.events[5].evidence_id == aligned.events[4].evidence_id
    assert aligned.events[1].raw_label == "old_fan_pulled_out"
    assert len(fake.json_calls) == 1


def test_matcher_ignores_labels_outside_vocabulary():
    fake = FakeLLM(json_handler=lambda *_: {"matches": [{"observed": "fan_gone", "steps": ["made_up_step"]}]})
    aligned, records = align(_observation(("fan_gone", "x")), VOCAB, llm_matcher(fake, "m"))
    assert records[0]["method"] == "unmatched" and aligned.events[0].label == "fan_gone"


def test_alignment_without_matcher_keeps_unknown_labels():
    aligned, records = align(_observation(("fan_gone", "x")), VOCAB, None)
    assert records[0]["method"] == "unmatched"
    assert aligned.events[0].label == "fan_gone"


def test_traceability_of_demo_run(reference, observation_fixture):
    requirement_set, _, manual_evidence, _ = reference
    fixture, _ = observation_fixture("fan_replacement_B")
    observation, video_evidence = observation_with_evidence(fixture["observation"], "V-001")
    report = VerificationReport(
        run_id="V-001", manual_id=requirement_set.source_id, video_id=None, procedure="p",
        verdicts=evaluate(requirement_set, observation),
    )
    evidence = {e.evidence_id: e for e in manual_evidence + video_evidence}
    assert traceability(report, evidence) == (1.0, [])

    missing = dict(evidence)
    missing.pop(report.verdicts[2].requirement_evidence_ids[0])
    ratio, issues = traceability(report, missing)
    assert ratio < 1.0 and any("R-003" in issue for issue in issues)
