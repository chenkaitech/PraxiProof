from praxiproof.ir.requirement import Requirement
from praxiproof.ir.verification import Status, Verdict
from praxiproof.verifier.events import EventIndex, unseen_verdict, verdict


def check_must_have(req: Requirement, index: EventIndex) -> Verdict:
    label = req.constraint.event
    seen = index.confident(label)
    if seen:
        return verdict(req, Status.PASS, f"{label} observed", seen)
    return unseen_verdict(req, index, [label], absence_is_violation=True, context="the step is mandatory")


def check_must_not(req: Requirement, index: EventIndex) -> Verdict:
    label = req.constraint.event
    seen = index.confident(label)
    if seen:
        return verdict(req, Status.VIOLATION, f"prohibited action {label} observed", seen)
    weak = index.weak(label)
    if weak:
        return verdict(
            req,
            Status.UNVERIFIED,
            f"possible prohibited action {label} detected with low confidence",
            weak,
            needed_evidence=f"A clearer view to confirm whether {label} happened",
        )
    if not req.observable:
        return verdict(
            req,
            Status.UNVERIFIED,
            f"{label} would not be visible in the video",
            needed_evidence=f"Separate evidence that {label} did not happen",
        )
    if index.complete:
        return verdict(req, Status.PASS, f"{label} not observed across the full video")
    return verdict(
        req,
        Status.INSUFFICIENT_EVIDENCE,
        f"{label} not observed, but the video does not cover the whole procedure",
        needed_evidence="Full video coverage of the procedure",
    )


def check_count(req: Requirement, index: EventIndex) -> Verdict:
    label, minimum = req.constraint.event, req.constraint.min_count
    seen, weak = index.confident(label), index.weak(label)
    measured = {"observed_count": len(seen), "required_count": minimum}
    if len(seen) >= minimum:
        return verdict(req, Status.PASS, f"{label} observed {len(seen)} times (≥ {minimum})", seen, measured)
    if len(seen) + len(weak) >= minimum:
        return verdict(
            req,
            Status.UNVERIFIED,
            f"{label} observed {len(seen)} times confidently, {len(weak)} more with low confidence",
            seen + weak,
            measured,
            needed_evidence=f"A clearer view of each {label}",
        )
    if not req.observable:
        return verdict(req, Status.UNVERIFIED, f"{label} would not be visible in the video", seen, measured)
    if index.complete:
        return verdict(req, Status.VIOLATION, f"{label} observed {len(seen)} times, {minimum} required", seen, measured)
    return verdict(req, Status.INSUFFICIENT_EVIDENCE, f"only {len(seen)} of {minimum} {label} observed", seen, measured)
