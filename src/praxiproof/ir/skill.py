import re

from pydantic import BaseModel, Field, model_validator

SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillStep(BaseModel):
    event: str
    instruction: str
    evidence_ids: list[str] = Field(default_factory=list)


class SkillRule(BaseModel):
    rule_id: str
    statement: str
    constraint: str
    severity: str
    category: str
    evidence_ids: list[str] = Field(default_factory=list)


class SkillIR(BaseModel):
    name: str
    description: str
    goal: str
    preconditions: list[SkillRule]
    steps: list[SkillStep]
    rules: list[SkillRule]
    verified_by_run: str
    verification_summary: dict[str, int]

    @model_validator(mode="after")
    def _spec(self) -> "SkillIR":
        if len(self.name) > 64 or not SKILL_NAME.match(self.name):
            raise ValueError("skill name must be lowercase alphanumeric words joined by single hyphens, max 64 chars")
        if not self.description or len(self.description) > 1024:
            raise ValueError("skill description must be 1-1024 characters")
        return self
