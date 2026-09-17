from praxiproof.ir.requirement import Requirement
from praxiproof.ir.verification import Status, Verdict
from praxiproof.verifier.events import EventIndex, unseen_verdict, verdict


def check_must_have(req: Requirement, index: EventIndex) -> Verdict:
    label = req.constraint.event
    seen = index.confident(label)
    if seen:
        return verdict(req, Status.PASS, "must_have.pass", {"event": label}, seen)
    return unseen_verdict(req, index, [label], absence_is_violation=True, context="ctx.mandatory")


def check_must_not(req: Requirement, index: EventIndex) -> Verdict:
    label = req.constraint.event
    params = {"event": label}
    seen = index.confident(label)
    if seen:
        return verdict(req, Status.VIOLATION, "must_not.violation", params, seen)
    weak = index.weak(label)
    if weak:
        return verdict(req, Status.UNVERIFIED, "must_not.weak", params, weak, needed="needed.confirm_absent")
    if not req.observable:
        return verdict(req, Status.UNVERIFIED, "must_not.hidden", params, needed="needed.separate_absent")
    if index.complete:
        return verdict(req, Status.PASS, "must_not.pass", params)
    return verdict(req, Status.INSUFFICIENT_EVIDENCE, "must_not.insufficient", params, needed="needed.full_coverage")


def check_count(req: Requirement, index: EventIndex) -> Verdict:
    label, minimum = req.constraint.event, req.constraint.min_count
    seen, weak = index.confident(label), index.weak(label)
    measured = {"observed_count": len(seen), "required_count": minimum}
    params = {"event": label, "count": str(len(seen)), "minimum": str(minimum), "weak": str(len(weak))}
    if len(seen) >= minimum:
        return verdict(req, Status.PASS, "count.pass", params, seen, measured)
    if len(seen) + len(weak) >= minimum:
        return verdict(req, Status.UNVERIFIED, "count.weak", params, seen + weak, measured, needed="needed.clearer_each")
    if not req.observable:
        return verdict(req, Status.UNVERIFIED, "count.hidden", params, seen, measured)
    if index.approximate and seen:
        return verdict(req, Status.UNVERIFIED, "count.approximate", params, seen, measured, needed="needed.count_review")
    if index.complete:
        return verdict(req, Status.VIOLATION, "count.violation", params, seen, measured)
    return verdict(req, Status.INSUFFICIENT_EVIDENCE, "count.insufficient", params, seen, measured)
