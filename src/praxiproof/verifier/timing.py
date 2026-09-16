from praxiproof.ir.requirement import Requirement
from praxiproof.ir.verification import Status, Verdict
from praxiproof.verifier.events import EventIndex, unseen_verdict, verdict


def check_max_interval(req: Requirement, index: EventIndex) -> Verdict:
    a, b, limit = req.constraint.a, req.constraint.b, req.constraint.seconds
    starts = index.confident(a)
    if not starts:
        return unseen_verdict(req, index, [a], absence_is_violation=False, context=f"interval to {b} not measurable")

    ends = index.confident(b)
    worst = None
    for i, start in enumerate(starts):
        follow = next((e for e in ends if e.end > start.end), None)
        if i + 1 < len(starts) and (follow is None or starts[i + 1].end < follow.end):
            continue
        if follow is None:
            remaining = index.observation.duration - start.end - start.time_uncertainty
            measured = {"observed_seconds": None, "required_seconds": limit, "video_remaining_seconds": round(remaining, 1)}
            if index.complete and remaining > limit:
                return verdict(
                    req, Status.VIOLATION, f"{b} never observed within {limit:g}s after {a}", [start], measured
                )
            return unseen_verdict(req, index, [b], absence_is_violation=False, context=f"no {b} after {a}")
        interval = follow.end - start.end
        uncertainty = start.time_uncertainty + follow.time_uncertainty
        candidate = (interval, uncertainty, start, follow)
        if worst is None or interval - uncertainty > worst[0] - worst[1]:
            worst = candidate

    interval, uncertainty, start, follow = worst
    measured = {
        "observed_seconds": round(interval, 1),
        "uncertainty_seconds": round(uncertainty, 1),
        "required_seconds": limit,
    }
    events = [start, follow]
    if interval - uncertainty > limit:
        return verdict(
            req, Status.VIOLATION, f"{a} → {b} took {interval:.1f}s (±{uncertainty:.1f}s), limit {limit:g}s", events, measured
        )
    if interval + uncertainty <= limit:
        return verdict(req, Status.PASS, f"{a} → {b} took {interval:.1f}s, within {limit:g}s", events, measured)
    return verdict(
        req,
        Status.UNVERIFIED,
        f"{a} → {b} took {interval:.1f}s ±{uncertainty:.1f}s, too close to the {limit:g}s limit to decide",
        events,
        measured,
        needed_evidence="More precise timestamps for both events",
    )
