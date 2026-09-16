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
        return unseen_verdict(req, index, [b], absence_is_violation=False, context=f"cannot check {a} before {b}")
    if not index.confident(a):
        return unseen_verdict(req, index, [a], absence_is_violation=True, context=f"it must happen before {b}")
    first_a, first_b = index.confident(a)[0], index.confident(b)[0]
    return _ordered_verdict(req, first_a, first_b, a, b)


def check_after(req: Requirement, index: EventIndex) -> Verdict:
    a, b = req.constraint.a, req.constraint.b
    if not index.confident(b):
        return unseen_verdict(req, index, [b], absence_is_violation=False, context=f"cannot check {a} after {b}")
    if not index.confident(a):
        return unseen_verdict(req, index, [a], absence_is_violation=True, context=f"it must happen after {b}")
    last_a, last_b = index.confident(a)[-1], index.confident(b)[-1]
    return _ordered_verdict(req, last_b, last_a, b, a)


def check_precondition(req: Requirement, index: EventIndex) -> Verdict:
    a, b = req.constraint.a, req.constraint.b
    if not index.confident(b):
        return unseen_verdict(req, index, [b], absence_is_violation=False, context=f"precondition {a} not assessable")
    first_b = index.confident(b)[0]
    prior = [e for e in index.confident(a) if _compare(e, first_b) == 1]
    if prior:
        return verdict(req, Status.PASS, f"{a} established before {b}", [prior[0], first_b])
    later = index.confident(a)
    if not later:
        return unseen_verdict(req, index, [a], absence_is_violation=True, context=f"required before {b}")
    events = [later[0], first_b]
    if all(_compare(e, first_b) == -1 for e in later):
        return verdict(req, Status.VIOLATION, f"{a} was only established after {b} started", events)
    return verdict(
        req,
        Status.UNVERIFIED,
        f"{a} and {b} are too close in time to confirm the precondition",
        events,
        needed_evidence=f"Precise timing of {a}",
    )


def _ordered_verdict(req: Requirement, earlier: ObservedEvent, later: ObservedEvent, e_label: str, l_label: str) -> Verdict:
    order = _compare(earlier, later)
    events = [earlier, later]
    measured = {"gap_seconds": round(later.start - earlier.start, 2)}
    if order == 1:
        return verdict(req, Status.PASS, f"{e_label} precedes {l_label}", events, measured)
    if order == -1:
        return verdict(req, Status.VIOLATION, f"{l_label} happened before {e_label}", events, measured)
    return verdict(
        req,
        Status.UNVERIFIED,
        f"{e_label} and {l_label} are too close in time to determine order",
        events,
        measured,
        needed_evidence="Finer timing of both events",
    )
