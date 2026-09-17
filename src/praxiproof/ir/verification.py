from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from praxiproof.constraints.schema import Constraint


class Status(StrEnum):
    PASS = "PASS"
    VIOLATION = "VIOLATION"
    UNVERIFIED = "UNVERIFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Verdict(BaseModel):
    rule_id: str
    status: Status
    reason: str
    constraint: Constraint
    category: Literal["safety", "procedure", "verification"]
    severity: Literal["critical", "major", "minor"]
    statement: str
    observed_event_ids: list[str] = Field(default_factory=list)
    requirement_evidence_ids: list[str] = Field(default_factory=list)
    observation_evidence_ids: list[str] = Field(default_factory=list)
    reason_code: str | None = None
    reason_params: dict[str, str] = Field(default_factory=dict)
    measured: dict[str, Any] | None = None
    needed_evidence: str | None = None
    needed_code: str | None = None
    review: Literal["accepted", "rejected"] | None = None


class VerificationReport(BaseModel):
    run_id: str
    manual_id: str
    video_id: str | None
    procedure: str
    verdicts: list[Verdict]
    alignment: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Status}
        for v in self.verdicts:
            counts[v.status.value] += 1
        return counts

    def overall(self) -> Status:
        statuses = {v.status for v in self.verdicts}
        for status in (Status.VIOLATION, Status.INSUFFICIENT_EVIDENCE, Status.UNVERIFIED):
            if status in statuses:
                return status
        return Status.PASS
