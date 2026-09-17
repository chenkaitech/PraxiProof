from collections import defaultdict
from dataclasses import dataclass

from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.ir.requirement import Requirement
from praxiproof.ir.verification import Status, Verdict
from praxiproof.verifier.messages import render


@dataclass
class EventIndex:
    observation: Observation
    min_confidence: float

    def __post_init__(self) -> None:
        self._confident: dict[str, list[ObservedEvent]] = defaultdict(list)
        self._weak: dict[str, list[ObservedEvent]] = defaultdict(list)
        for event in self.observation.sorted_events():
            bucket = self._confident if event.confidence >= self.min_confidence else self._weak
            bucket[event.label].append(event)

    @property
    def complete(self) -> bool:
        return self.observation.complete

    @property
    def approximate(self) -> bool:
        return self.observation.approximate

    def confident(self, label: str) -> list[ObservedEvent]:
        return self._confident.get(label, [])

    def weak(self, label: str) -> list[ObservedEvent]:
        return self._weak.get(label, [])


def verdict(
    req: Requirement,
    status: Status,
    code: str,
    params: dict[str, str],
    events: list[ObservedEvent] = (),
    measured: dict | None = None,
    needed: str | None = None,
) -> Verdict:
    return Verdict(
        rule_id=req.rule_id,
        status=status,
        reason=render(code, params),
        reason_code=code,
        reason_params=params,
        needed_code=needed,
        needed_evidence=render(needed, params) if needed else None,
        constraint=req.constraint,
        category=req.category,
        severity=req.severity,
        statement=req.statement,
        observed_event_ids=[e.event_id for e in events],
        requirement_evidence_ids=list(req.evidence_ids),
        observation_evidence_ids=[e.evidence_id for e in events if e.evidence_id],
        measured=measured,
    )


def unseen_verdict(
    req: Requirement, index: EventIndex, missing: list[str], absence_is_violation: bool, context: str
) -> Verdict:
    weak = [e for label in missing for e in index.weak(label)]
    params = {"events": ", ".join(missing), "context": context, "a": req.constraint.a or "", "b": req.constraint.b or ""}
    if weak:
        return verdict(req, Status.UNVERIFIED, "unseen.weak", params, weak, needed="needed.clearer_view")
    if not req.observable:
        return verdict(req, Status.UNVERIFIED, "unseen.hidden", params, needed="needed.separate")
    if absence_is_violation and index.complete:
        return verdict(req, Status.VIOLATION, "unseen.violation", params)
    return verdict(req, Status.INSUFFICIENT_EVIDENCE, "unseen.insufficient", params, needed="needed.coverage")
