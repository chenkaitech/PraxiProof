import pytest

from praxiproof.constraints.engine import evaluate
from praxiproof.constraints.schema import Constraint
from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.ir.requirement import EventDef, Requirement, RequirementSet
from praxiproof.ir.verification import Status


@pytest.mark.parametrize("name", ["fan_replacement_A", "fan_replacement_B", "fan_replacement_C"])
def test_demo_scenarios_match_expected_verdicts(reference, observation_fixture, name):
    requirement_set = reference[0]
    fixture, observation = observation_fixture(name)
    verdicts = {v.rule_id: v.status.value for v in evaluate(requirement_set, observation)}
    assert verdicts == fixture["expected"]


def test_timing_violation_reports_measurement(reference, observation_fixture):
    _, observation = observation_fixture("fan_replacement_C")
    verdict = next(v for v in evaluate(reference[0], observation) if v.rule_id == "R-003")
    assert verdict.measured == {"observed_seconds": 45.0, "uncertainty_seconds": 1.0, "required_seconds": 30}
    assert verdict.observed_event_ids == ["O-005", "O-006"]


def _rules(*constraints: dict, observable: bool = True) -> RequirementSet:
    labels = sorted({v for c in constraints for k, v in c.items() if k in ("event", "a", "b")})
    return RequirementSet(
        source_id="M",
        procedure="test",
        events=[EventDef(label=label, description=label) for label in labels],
        requirements=[
            Requirement(
                rule_id=f"R-{i:03d}",
                statement="s",
                constraint=Constraint.model_validate(c),
                category="procedure",
                severity="major",
                observable=observable,
            )
            for i, c in enumerate(constraints, start=1)
        ],
    )


def _obs(*events: tuple, complete: bool = True, duration: float = 100.0) -> Observation:
    return Observation(
        source_id="V",
        duration=duration,
        complete=complete,
        backend="test",
        events=[
            ObservedEvent(event_id=f"O-{i}", label=label, start=start, end=end, time_uncertainty=unc, confidence=conf)
            for i, (label, start, end, unc, conf) in enumerate(events, start=1)
        ],
    )


def _status(rules: RequirementSet, observation: Observation) -> list[Status]:
    return [v.status for v in evaluate(rules, observation)]


def test_must_have_statuses():
    rules = _rules({"type": "MUST_HAVE", "event": "check_done"})
    assert _status(rules, _obs(("check_done", 1, 2, 0, 0.9))) == [Status.PASS]
    assert _status(rules, _obs()) == [Status.VIOLATION]
    assert _status(rules, _obs(complete=False)) == [Status.INSUFFICIENT_EVIDENCE]
    assert _status(rules, _obs(("check_done", 1, 2, 0, 0.3))) == [Status.UNVERIFIED]
    hidden = _rules({"type": "MUST_HAVE", "event": "check_done"}, observable=False)
    assert _status(hidden, _obs()) == [Status.UNVERIFIED]


def test_must_not_statuses():
    rules = _rules({"type": "MUST_NOT", "event": "cover_forced"})
    assert _status(rules, _obs()) == [Status.PASS]
    assert _status(rules, _obs(("cover_forced", 3, 4, 0, 0.8))) == [Status.VIOLATION]
    assert _status(rules, _obs(("cover_forced", 3, 4, 0, 0.2))) == [Status.UNVERIFIED]
    assert _status(rules, _obs(complete=False)) == [Status.INSUFFICIENT_EVIDENCE]


def test_count_statuses():
    rules = _rules({"type": "COUNT", "event": "screw_loosened", "min_count": 3})
    screws = [("screw_loosened", t, t + 1, 0, 0.9) for t in (1, 5, 9)]
    assert _status(rules, _obs(*screws)) == [Status.PASS]
    assert _status(rules, _obs(*screws[:2])) == [Status.VIOLATION]
    assert _status(rules, _obs(*screws[:2], ("screw_loosened", 12, 13, 0, 0.3))) == [Status.UNVERIFIED]


def test_order_statuses():
    rules = _rules({"type": "BEFORE", "a": "power_off", "b": "cover_opened"})
    assert _status(rules, _obs(("power_off", 1, 2, 0.5, 0.9), ("cover_opened", 10, 12, 0.5, 0.9))) == [Status.PASS]
    assert _status(rules, _obs(("power_off", 10, 12, 0.5, 0.9), ("cover_opened", 1, 2, 0.5, 0.9))) == [Status.VIOLATION]
    assert _status(rules, _obs(("power_off", 5, 6, 1.0, 0.9), ("cover_opened", 5.5, 7, 1.0, 0.9))) == [Status.UNVERIFIED]
    assert _status(rules, _obs(("cover_opened", 1, 2, 0, 0.9))) == [Status.VIOLATION]
    assert _status(rules, _obs(("power_off", 1, 2, 0, 0.9))) == [Status.INSUFFICIENT_EVIDENCE]
    assert _status(rules, _obs(("cover_opened", 1, 2, 0, 0.9), complete=False)) == [Status.INSUFFICIENT_EVIDENCE]

    after = _rules({"type": "AFTER", "a": "health_checked", "b": "fan_inserted"})
    assert _status(after, _obs(("fan_inserted", 1, 2, 0, 0.9), ("health_checked", 8, 9, 0, 0.9))) == [Status.PASS]
    assert _status(after, _obs(("health_checked", 1, 2, 0, 0.9), ("fan_inserted", 8, 9, 0, 0.9))) == [Status.VIOLATION]
    assert _status(after, _obs(("fan_inserted", 1, 2, 0, 0.9))) == [Status.VIOLATION]
    assert _status(after, _obs(("health_checked", 1, 2, 0, 0.9))) == [Status.INSUFFICIENT_EVIDENCE]
    hidden = _rules({"type": "AFTER", "a": "health_checked", "b": "fan_inserted"}, observable=False)
    assert _status(hidden, _obs(("fan_inserted", 1, 2, 0, 0.9))) == [Status.UNVERIFIED]


def test_precondition_statuses():
    rules = _rules({"type": "PRECONDITION", "a": "power_off", "b": "cover_opened"})
    assert _status(rules, _obs(("power_off", 1, 2, 0, 0.9), ("cover_opened", 10, 12, 0, 0.9))) == [Status.PASS]
    assert _status(rules, _obs(("cover_opened", 1, 2, 0, 0.9), ("power_off", 10, 12, 0, 0.9))) == [Status.VIOLATION]
    assert _status(rules, _obs(("cover_opened", 1, 2, 0, 0.9))) == [Status.VIOLATION]
    hidden = _rules({"type": "PRECONDITION", "a": "power_off", "b": "cover_opened"}, observable=False)
    assert _status(hidden, _obs(("cover_opened", 1, 2, 0, 0.9))) == [Status.UNVERIFIED]


def test_max_interval_statuses():
    rules = _rules({"type": "MAX_INTERVAL", "a": "fan_removed", "b": "fan_inserted", "seconds": 30})
    assert _status(rules, _obs(("fan_removed", 0, 5, 0.5, 0.9), ("fan_inserted", 20, 25, 0.5, 0.9))) == [Status.PASS]
    assert _status(rules, _obs(("fan_removed", 0, 5, 0.5, 0.9), ("fan_inserted", 34, 40, 0.5, 0.9))) == [Status.VIOLATION]
    assert _status(rules, _obs(("fan_removed", 0, 5, 1.0, 0.9), ("fan_inserted", 30, 35.5, 1.0, 0.9))) == [Status.UNVERIFIED]
    assert _status(rules, _obs(("fan_removed", 0, 5, 0.5, 0.9), ("fan_inserted", 30, 36, 0.5, 0.9))) == [Status.UNVERIFIED]
    assert _status(rules, _obs(("fan_removed", 0, 5, 0.5, 0.9))) == [Status.VIOLATION]
    assert _status(rules, _obs(("fan_removed", 80, 85, 0.5, 0.9))) == [Status.INSUFFICIENT_EVIDENCE]
    assert _status(rules, _obs(("fan_inserted", 20, 25, 0.5, 0.9))) == [Status.INSUFFICIENT_EVIDENCE]


def test_max_interval_measures_from_latest_start_before_end():
    rules = _rules({"type": "MAX_INTERVAL", "a": "fan_removed", "b": "fan_inserted", "seconds": 30})
    observation = _obs(
        ("fan_removed", 60, 62, 0.5, 0.9),
        ("fan_removed", 72, 76.8, 0.5, 0.9),
        ("fan_inserted", 115, 121.8, 0.5, 0.9),
    )
    verdict = evaluate(rules, observation)[0]
    assert verdict.measured["observed_seconds"] == 45.0
    assert verdict.observed_event_ids == ["O-2", "O-3"]

    unfinished = evaluate(rules, _obs(("fan_removed", 10, 12, 0.5, 0.9), ("fan_removed", 70, 75, 0.5, 0.9)))[0]
    assert unfinished.status == Status.INSUFFICIENT_EVIDENCE
    assert unfinished.observed_event_ids == []


def test_max_interval_uses_worst_repetition():
    rules = _rules({"type": "MAX_INTERVAL", "a": "fan_removed", "b": "fan_inserted", "seconds": 30})
    observation = _obs(
        ("fan_removed", 0, 5, 0.5, 0.9),
        ("fan_inserted", 10, 15, 0.5, 0.9),
        ("fan_removed", 40, 45, 0.5, 0.9),
        ("fan_inserted", 85, 90, 0.5, 0.9),
    )
    verdict = evaluate(rules, observation)[0]
    assert verdict.status == Status.VIOLATION
    assert verdict.measured["observed_seconds"] == 45.0
