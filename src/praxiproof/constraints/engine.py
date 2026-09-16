from collections.abc import Callable

from praxiproof.constraints.schema import ConstraintType
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import Requirement, RequirementSet
from praxiproof.ir.verification import Verdict
from praxiproof.verifier.events import EventIndex
from praxiproof.verifier.mandatory import check_count, check_must_have, check_must_not
from praxiproof.verifier.ordering import check_after, check_before, check_precondition
from praxiproof.verifier.timing import check_max_interval

_CHECKS: dict[ConstraintType, Callable[[Requirement, EventIndex], Verdict]] = {
    ConstraintType.MUST_HAVE: check_must_have,
    ConstraintType.MUST_NOT: check_must_not,
    ConstraintType.COUNT: check_count,
    ConstraintType.BEFORE: check_before,
    ConstraintType.AFTER: check_after,
    ConstraintType.PRECONDITION: check_precondition,
    ConstraintType.MAX_INTERVAL: check_max_interval,
}


def evaluate(requirements: RequirementSet, observation: Observation, min_confidence: float = 0.5) -> list[Verdict]:
    index = EventIndex(observation, min_confidence)
    return [_CHECKS[req.constraint.type](req, index) for req in requirements.requirements]
