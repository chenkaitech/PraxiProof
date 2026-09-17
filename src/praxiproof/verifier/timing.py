from praxiproof.ir.requirement import Requirement
from praxiproof.ir.verification import Status, Verdict
from praxiproof.verifier.events import EventIndex, unseen_verdict, verdict


def check_max_interval(req: Requirement, index: EventIndex) -> Verdict:
    a, b, limit = req.constraint.a, req.constraint.b, req.constraint.seconds
    starts = index.confident(a)
    if not starts:
        return unseen_verdict(req, index, [a], absence_is_violation=False, context="ctx.interval_unmeasurable")

    ends = index.confident(b)
    params = {"a": a, "b": b, "limit": f"{limit:g}"}
    worst = None
    for i, start in enumerate(starts):
        follow = next((e for e in ends if e.end > start.end), None)
        if i + 1 < len(starts) and (follow is None or starts[i + 1].end < follow.end):
            continue
        if follow is None:
            remaining = index.observation.duration - start.end - start.time_uncertainty
            measured = {"observed_seconds": None, "required_seconds": limit, "video_remaining_seconds": round(remaining, 1)}
            if index.complete and remaining > limit:
                return verdict(req, Status.VIOLATION, "interval.never", params, [start], measured)
            return unseen_verdict(req, index, [b], absence_is_violation=False, context="ctx.no_follow")
        interval = follow.end - start.end
        uncertainty = start.time_uncertainty + follow.time_uncertainty
        if worst is None or interval - uncertainty > worst[0] - worst[1]:
            worst = (interval, uncertainty, start, follow)

    interval, uncertainty, start, follow = worst
    measured = {
        "observed_seconds": round(interval, 1),
        "uncertainty_seconds": round(uncertainty, 1),
        "required_seconds": limit,
    }
    params |= {"interval": f"{interval:.1f}", "uncertainty": f"{uncertainty:.1f}"}
    events = [start, follow]
    if interval - uncertainty > limit:
        return verdict(req, Status.VIOLATION, "interval.violation", params, events, measured)
    if interval + uncertainty <= limit:
        return verdict(req, Status.PASS, "interval.pass", params, events, measured)
    return verdict(req, Status.UNVERIFIED, "interval.too_close", params, events, measured, needed="needed.precise_both")
