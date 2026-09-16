import re
from enum import StrEnum

from pydantic import BaseModel, model_validator

EVENT_LABEL = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class ConstraintType(StrEnum):
    MUST_HAVE = "MUST_HAVE"
    MUST_NOT = "MUST_NOT"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    MAX_INTERVAL = "MAX_INTERVAL"
    PRECONDITION = "PRECONDITION"
    COUNT = "COUNT"


_REQUIRED_FIELDS: dict[ConstraintType, tuple[str, ...]] = {
    ConstraintType.MUST_HAVE: ("event",),
    ConstraintType.MUST_NOT: ("event",),
    ConstraintType.BEFORE: ("a", "b"),
    ConstraintType.AFTER: ("a", "b"),
    ConstraintType.MAX_INTERVAL: ("a", "b", "seconds"),
    ConstraintType.PRECONDITION: ("a", "b"),
    ConstraintType.COUNT: ("event", "min_count"),
}


class Constraint(BaseModel):
    """Field meaning by type:
    MUST_HAVE/MUST_NOT: `event` must / must not be observed.
    BEFORE: `a` occurs before `b`.  AFTER: `a` occurs after `b`.
    MAX_INTERVAL: at most `seconds` from completion of `a` to completion of the next `b`.
    PRECONDITION: state/action `a` is established before action `b`.
    COUNT: `event` observed at least `min_count` times.
    """

    type: ConstraintType
    event: str | None = None
    a: str | None = None
    b: str | None = None
    seconds: float | None = None
    min_count: int | None = None

    @model_validator(mode="after")
    def _check_fields(self) -> "Constraint":
        required = _REQUIRED_FIELDS[self.type]
        missing = [name for name in required if getattr(self, name) is None]
        if missing:
            raise ValueError(f"{self.type} requires {', '.join(missing)}")
        for name in ("event", "a", "b"):
            value = getattr(self, name)
            if name not in required:
                if value is not None:
                    raise ValueError(f"{self.type} does not use '{name}'")
                continue
            if not EVENT_LABEL.match(value):
                raise ValueError(f"event label '{value}' must be snake_case")
        if self.seconds is not None and (self.type != ConstraintType.MAX_INTERVAL or self.seconds <= 0):
            raise ValueError("seconds must be positive and only used by MAX_INTERVAL")
        if self.min_count is not None and (self.type != ConstraintType.COUNT or self.min_count < 1):
            raise ValueError("min_count must be >= 1 and only used by COUNT")
        if self.a is not None and self.a == self.b:
            raise ValueError("a and b must be different events")
        return self

    def events(self) -> list[str]:
        return [e for e in (self.event, self.a, self.b) if e]

    def signature(self) -> str:
        if self.type in (ConstraintType.MUST_HAVE, ConstraintType.MUST_NOT):
            return f"{self.type}({self.event})"
        if self.type == ConstraintType.COUNT:
            return f"{self.type}({self.event}>={self.min_count})"
        if self.type == ConstraintType.MAX_INTERVAL:
            return f"{self.type}({self.a}->{self.b}<={self.seconds:g}s)"
        return f"{self.type}({self.a},{self.b})"
