from pydantic import BaseModel, Field, model_validator


class ObservedEvent(BaseModel):
    event_id: str
    label: str
    description: str = ""
    start: float
    end: float
    time_uncertainty: float = 0.0
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_id: str | None = None
    raw_label: str | None = None

    @model_validator(mode="after")
    def _times(self) -> "ObservedEvent":
        if self.end < self.start:
            raise ValueError(f"{self.event_id}: end must not precede start")
        return self


class Observation(BaseModel):
    source_id: str
    duration: float
    complete: bool = True
    backend: str
    model: str | None = None
    events: list[ObservedEvent]

    def sorted_events(self) -> list[ObservedEvent]:
        return sorted(self.events, key=lambda e: (e.start, e.end))
