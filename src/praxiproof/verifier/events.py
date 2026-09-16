from collections import defaultdict
from dataclasses import dataclass

from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.ir.requirement import Requirement
from praxiproof.ir.verification import Status, Verdict


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

    def confident(self, label: str) -> list[ObservedEvent]:
        return self._confident.get(label, [])

    def weak(self, label: str) -> list[ObservedEvent]:
        return self._weak.get(label, [])


def verdict(
    req: Requirement,
    status: Status,
    reason: str,
    events: list[ObservedEvent] = (),
    measured: dict | None = None,
    needed_evidence: str | None = None,
) -> Verdict:
    return Verdict(
        rule_id=req.rule_id,
        status=status,
        reason=reason,
        constraint=req.constraint,
        category=req.category,
        severity=req.severity,
        statement=req.statement,
        observed_event_ids=[e.event_id for e in events],
        requirement_evidence_ids=list(req.evidence_ids),
        observation_evidence_ids=[e.evidence_id for e in events if e.evidence_id],
        measured=measured,
        needed_evidence=needed_evidence,
    )


def unseen_verdict(
    req: Requirement, index: EventIndex, missing: list[str], absence_is_violation: bool, context: str
) -> Verdict:
    weak = [e for label in missing for e in index.weak(label)]
    names = ", ".join(missing)
    if weak:
        return verdict(
            req,
            Status.UNVERIFIED,
            f"{names} only detected with low confidence; {context}",
            weak,
            needed_evidence=f"A clearer view of: {names}",
        )
    if not req.observable:
        return verdict(
            req,
            Status.UNVERIFIED,
            f"{names} is not expected to be visible in the operation video; {context}",
            needed_evidence=f"Separate evidence (log, screenshot, or another camera angle) showing: {names}",
        )
    if absence_is_violation and index.complete:
        return verdict(req, Status.VIOLATION, f"{names} was not observed anywhere in the video; {context}")
    return verdict(
        req,
        Status.INSUFFICIENT_EVIDENCE,
        f"{names} was not observed; {context}",
        needed_evidence=f"Video coverage that includes: {names}",
    )
