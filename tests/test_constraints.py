import pytest
from pydantic import ValidationError

from praxiproof.constraints.schema import Constraint
from praxiproof.ir.requirement import EventDef, Requirement, RequirementSet


@pytest.mark.parametrize(
    "fields",
    [
        {"type": "MUST_HAVE"},
        {"type": "BEFORE", "a": "x_done"},
        {"type": "MAX_INTERVAL", "a": "x_done", "b": "y_done"},
        {"type": "COUNT", "event": "screw_loosened"},
        {"type": "MUST_HAVE", "event": "Fan Removed"},
        {"type": "BEFORE", "a": "x_done", "b": "y_done", "event": "z_done"},
        {"type": "MUST_HAVE", "event": "x_done", "seconds": 3},
        {"type": "MAX_INTERVAL", "a": "x_done", "b": "y_done", "seconds": 0},
        {"type": "AFTER", "a": "x_done", "b": "x_done"},
    ],
)
def test_invalid_constraints_are_rejected(fields):
    with pytest.raises(ValidationError):
        Constraint.model_validate(fields)


def test_signatures():
    assert Constraint(type="MAX_INTERVAL", a="fan_removed", b="fan_inserted", seconds=30).signature() == (
        "MAX_INTERVAL(fan_removed->fan_inserted<=30s)"
    )
    assert Constraint(type="COUNT", event="screw_loosened", min_count=4).signature() == "COUNT(screw_loosened>=4)"
    assert Constraint(type="BEFORE", a="power_off", b="cover_opened").events() == ["power_off", "cover_opened"]


def test_requirement_set_rejects_undefined_events():
    with pytest.raises(ValidationError, match="undefined events"):
        RequirementSet(
            source_id="M",
            procedure="p",
            events=[EventDef(label="power_off", description="d")],
            requirements=[
                Requirement(
                    rule_id="R-001",
                    statement="s",
                    constraint=Constraint(type="BEFORE", a="power_off", b="cover_opened"),
                    category="safety",
                    severity="critical",
                )
            ],
        )


def test_reference_requirements_load_with_citations(reference):
    requirement_set, doc, evidence, quotes = reference
    assert len(requirement_set.requirements) == 8
    cited = {e.evidence_id: e for e in evidence}
    timing = next(r for r in requirement_set.requirements if r.constraint.type == "MAX_INTERVAL")
    assert "30 seconds" in cited[timing.evidence_ids[0]].text
    assert cited[timing.evidence_ids[0]].locator.section == "Replacing and Returning the Front Fan Module"
