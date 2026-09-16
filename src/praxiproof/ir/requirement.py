from typing import Literal

from pydantic import BaseModel, Field, model_validator

from praxiproof.constraints.schema import EVENT_LABEL, Constraint


class EventDef(BaseModel):
    label: str
    description: str

    @model_validator(mode="after")
    def _label(self) -> "EventDef":
        if not EVENT_LABEL.match(self.label):
            raise ValueError(f"event label '{self.label}' must be snake_case")
        return self


class Requirement(BaseModel):
    rule_id: str
    statement: str
    constraint: Constraint
    category: Literal["safety", "procedure", "verification"]
    severity: Literal["critical", "major", "minor"]
    observable: bool = True
    evidence_ids: list[str] = Field(default_factory=list)


class RequirementSet(BaseModel):
    source_id: str
    procedure: str
    events: list[EventDef]
    requirements: list[Requirement]
    compiler_model: str | None = None

    @model_validator(mode="after")
    def _events_defined(self) -> "RequirementSet":
        known = {e.label for e in self.events}
        for req in self.requirements:
            unknown = [e for e in req.constraint.events() if e not in known]
            if unknown:
                raise ValueError(f"{req.rule_id} references undefined events: {unknown}")
        ids = [r.rule_id for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("rule_id values must be unique")
        return self

    def event(self, label: str) -> EventDef | None:
        return next((e for e in self.events if e.label == label), None)
