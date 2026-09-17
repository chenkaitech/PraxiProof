import statistics

from praxiproof.ir.observation import ObservedEvent
from praxiproof.ir.requirement import Requirement
from praxiproof.ir.verification import Status, Verdict
from praxiproof.verifier.events import EventIndex, unseen_verdict, verdict


def _compare(first: ObservedEvent, second: ObservedEvent) -> int:
    """1 if first clearly starts before second, -1 if clearly after, 0 if within timing uncertainty."""
    margin = first.time_uncertainty + second.time_uncertainty
    if first.start + margin < second.start:
        return 1
    if second.start + margin < first.start:
        return -1
    return 0


def check_before(req: Requirement, index: EventIndex) -> Verdict:
    a, b = req.constraint.a, req.constraint.b
    if not index.confident(b):
        return unseen_verdict(req, index, [b], absence_is_violation=False, context="ctx.cannot_before")
    if not index.confident(a):
        return unseen_verdict(req, index, [a], absence_is_violation=True, context="ctx.must_before")
    result = _ordered_verdict(req, index.confident(a)[0], index.confident(b)[0], a, b)
    return _soften_isolated(result, req, index, earlier=a, later=b)


def check_after(req: Requirement, index: EventIndex) -> Verdict:
    a, b = req.constraint.a, req.constraint.b
    if not index.confident(b):
        return unseen_verdict(req, index, [b], absence_is_violation=False, context="ctx.cannot_after")
    if not index.confident(a):
        return unseen_verdict(req, index, [a], absence_is_violation=True, context="ctx.must_after")
    result = _ordered_verdict(req, index.confident(b)[-1], index.confident(a)[-1], b, a)
    return _soften_isolated(result, req, index, earlier=b, later=a)


def check_precondition(req: Requirement, index: EventIndex) -> Verdict:
    a, b = req.constraint.a, req.constraint.b
    params = {"a": a, "b": b}
    if not index.confident(b):
        return unseen_verdict(req, index, [b], absence_is_violation=False, context="ctx.precondition_unassessable")
    first_b = index.confident(b)[0]
    prior = [e for e in index.confident(a) if _compare(e, first_b) == 1]
    if prior:
        return verdict(req, Status.PASS, "precondition.pass", params, [prior[0], first_b])
    later = index.confident(a)
    if not later:
        return unseen_verdict(req, index, [a], absence_is_violation=True, context="ctx.required_before")
    events = [later[0], first_b]
    if all(_compare(e, first_b) == -1 for e in later):
        if index.approximate and _median_start(later) < _median_start(index.confident(b)):
            return verdict(req, Status.UNVERIFIED, "precondition.isolated", params, events, needed="needed.precondition_review")
        return verdict(req, Status.VIOLATION, "precondition.violation", params, events)
    return verdict(req, Status.UNVERIFIED, "precondition.too_close", params, events, needed="needed.precise_timing")


def _ordered_verdict(req: Requirement, earlier: ObservedEvent, later: ObservedEvent, e_label: str, l_label: str) -> Verdict:
    events = [earlier, later]
    measured = {"gap_seconds": round(later.start - earlier.start, 2)}
    params = {"earlier": e_label, "later": l_label}
    order = _compare(earlier, later)
    if order == 1:
        return verdict(req, Status.PASS, "order.pass", params, events, measured)
    if order == -1:
        return verdict(req, Status.VIOLATION, "order.violation", params, events, measured)
    return verdict(req, Status.UNVERIFIED, "order.too_close", params, events, measured, needed="needed.finer_timing")


def _median_start(events: list[ObservedEvent]) -> float:
    return statistics.median(e.start for e in events)


def _soften_isolated(result: Verdict, req: Requirement, index: EventIndex, earlier: str, later: str) -> Verdict:
    """With an approximate observer, one stray detection should not overturn an order the bulk of detections agree with."""
    if result.status != Status.VIOLATION or not index.approximate:
        return result
    if _median_start(index.confident(earlier)) >= _median_start(index.confident(later)):
        return result
    events = [e for e in index.observation.events if e.event_id in result.observed_event_ids]
    return verdict(
        req, Status.UNVERIFIED, "order.isolated", {"earlier": earlier, "later": later}, events, result.measured, needed="needed.order_review"
    )
