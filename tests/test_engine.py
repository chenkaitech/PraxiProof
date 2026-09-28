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
    assert verdict.reason == "fan_removed → fan_inserted took 45.0s (±1.0s), limit 30s"
    assert (verdict.reason_code, verdict.reason_params["interval"], verdict.reason_params["limit"]) == ("interval.violation", "45.0", "30")


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


def _obs(*events: tuple, complete: bool = True, duration: float = 100.0, approximate: bool = False) -> Observation:
    return Observation(
        source_id="V",
        duration=duration,
        complete=complete,
        approximate=approximate,
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
    v = evaluate(hidden, _obs())[0]
    assert v.reason == "check_done is not expected to be visible in the operation video; the step is mandatory"
    assert v.needed_evidence.startswith("Separate evidence") and v.needed_code == "needed.separate"


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


def test_order_statuses_catches_repeated_event_interleaving():
    """BEFORE(fan_installed, psu_installed) must fail when some fans are installed after a PSU, even though
    the first fan is well before the first PSU: comparing only first-vs-first (an earlier bug) missed this."""
    rules = _rules({"type": "BEFORE", "a": "fan_installed", "b": "psu_installed"})
    three_then_one_then_three = (
        [("fan_installed", t, t + 2, 0.2, 0.9) for t in (0, 5, 10)]
        + [("psu_installed", 15, 17, 0.2, 0.9)]
        + [("fan_installed", t, t + 2, 0.2, 0.9) for t in (20, 25, 30)]
    )
    assert _status(rules, _obs(*three_then_one_then_three)) == [Status.VIOLATION]

    all_fans_first = (
        [("fan_installed", t, t + 2, 0.2, 0.9) for t in (0, 5, 10, 15, 20, 25)]
        + [("psu_installed", t, t + 2, 0.2, 0.9) for t in (30, 35)]
    )
    assert _status(rules, _obs(*all_fans_first)) == [Status.PASS]

    after = _rules({"type": "AFTER", "a": "health_checked", "b": "fan_inserted"})
    one_checked_too_early = (
        [("fan_inserted", t, t + 2, 0.2, 0.9) for t in (0, 5, 10)]
        + [("health_checked", 7, 8, 0.2, 0.9)]
        + [("fan_inserted", t, t + 2, 0.2, 0.9) for t in (20, 25)]
        + [("health_checked", 30, 31, 0.2, 0.9)]
    )
    assert _status(after, _obs(*one_checked_too_early)) == [Status.VIOLATION]


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


def _verdict(rules: RequirementSet, observation: Observation):
    return evaluate(rules, observation)[0]


def test_approximate_observer_does_not_flag_count_shortfall():
    rules = _rules({"type": "COUNT", "event": "fan_installed", "min_count": 6})
    two = [("fan_installed", t, t + 5, 0.5, 0.8) for t in (10, 30)]
    assert _status(rules, _obs(*two)) == [Status.VIOLATION]
    v = _verdict(rules, _obs(*two, approximate=True))
    assert (v.status, v.reason_code, v.needed_code) == (Status.UNVERIFIED, "count.approximate", "needed.count_review")
    assert v.reason == "fan_installed observed 2 of 6 times; the video observer can miss repeated back-to-back actions"
    assert _status(rules, _obs(approximate=True)) == [Status.VIOLATION]


def test_approximate_observer_softens_isolated_order_conflicts():
    rules = _rules({"type": "BEFORE", "a": "fan_installed", "b": "psu_installed"})
    stray = [("fan_installed", t, t + 5, 0.5, 0.8) for t in (10, 20, 30)] + [("psu_installed", t, t + 5, 0.5, 0.8) for t in (4, 40, 50)]
    assert _status(rules, _obs(*stray)) == [Status.VIOLATION]
    v = _verdict(rules, _obs(*stray, approximate=True))
    assert (v.status, v.reason_code, v.needed_code) == (Status.UNVERIFIED, "order.isolated", "needed.order_review")
    assert v.observed_event_ids and v.observation_evidence_ids == []

    reversed_order = [("psu_installed", t, t + 5, 0.5, 0.8) for t in (5, 12)] + [("fan_installed", t, t + 5, 0.5, 0.8) for t in (30, 40)]
    assert _status(rules, _obs(*reversed_order, approximate=True)) == [Status.VIOLATION]


def test_approximate_observer_softens_isolated_after_and_precondition_conflicts():
    after = _rules({"type": "AFTER", "a": "health_checked", "b": "fan_inserted"})
    events = [("fan_inserted", t, t + 2, 0.5, 0.8) for t in (10, 12, 50)] + [("health_checked", t, t + 2, 0.5, 0.8) for t in (20, 25)]
    assert _status(after, _obs(*events)) == [Status.VIOLATION]
    assert _verdict(after, _obs(*events, approximate=True)).reason_code == "order.isolated"

    pre = _rules({"type": "PRECONDITION", "a": "power_off", "b": "cover_opened"})
    events = [("cover_opened", t, t + 2, 0.5, 0.8) for t in (2, 30, 35)] + [("power_off", 10, 12, 0.5, 0.8)]
    assert _status(pre, _obs(*events)) == [Status.VIOLATION]
    v = _verdict(pre, _obs(*events, approximate=True))
    assert (v.status, v.reason_code) == (Status.UNVERIFIED, "precondition.isolated")
