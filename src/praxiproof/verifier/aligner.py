from collections.abc import Callable
from typing import Any

from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import EventDef
from praxiproof.llm import LLM

Matcher = Callable[[list[EventDef], list[EventDef]], dict[str, list[str]]]


def llm_matcher(llm: LLM, model: str) -> Matcher:
    def match(observed: list[EventDef], vocabulary: list[EventDef]) -> dict[str, list[str]]:
        schema = {
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "observed": {"enum": [o.label for o in observed]},
                            "steps": {"type": "array", "items": {"enum": [v.label for v in vocabulary]}},
                        },
                        "required": ["observed", "steps"],
                    },
                }
            },
            "required": ["matches"],
        }
        result = llm.chat_json(
            model,
            [
                {
                    "role": "system",
                    "content": "You map actions observed in a video to the steps of a written procedure. "
                    "Match only when both describe the same physical action or state change. One observed action may "
                    "satisfy several steps when it clearly performs all of them. Preparatory actions (unlocking, loosening, "
                    "grasping, pointing) are not the step they prepare for. Use an empty list when no step "
                    "describes that action; never pick the closest-sounding step.",
                },
                {
                    "role": "user",
                    "content": f"Procedure steps:\n{_listing(vocabulary)}\n\nObserved actions:\n{_listing(observed)}\n\n"
                    "Return one entry for every observed action with the list of steps it performs.",
                },
            ],
            schema,
        )
        known = {v.label for v in vocabulary}
        mapping: dict[str, list[str]] = {o.label: [] for o in observed}
        for item in result.get("matches", []):
            if item.get("observed") in mapping:
                steps = [s for s in item.get("steps", []) if s in known]
                mapping[item["observed"]] = list(dict.fromkeys(mapping[item["observed"]] + steps))
        return mapping

    return match


def _listing(events: list[EventDef]) -> str:
    return "\n".join(f"- {e.label}: {e.description}" for e in events)


def align(
    observation: Observation, vocabulary: list[EventDef], matcher: Matcher | None = None
) -> tuple[Observation, list[dict[str, Any]]]:
    known = {e.label for e in vocabulary}
    pending: dict[str, EventDef] = {}
    for event in observation.events:
        if event.label not in known and event.label not in pending:
            pending[event.label] = EventDef.model_construct(label=event.label, description=event.description or event.label)
    mapping = matcher(list(pending.values()), vocabulary) if pending and matcher and vocabulary else {}

    aligned, records = [], []
    for event in observation.events:
        record = {"event_id": event.event_id, "observed_label": event.label}
        if event.label in known:
            aligned.append(event)
            records.append(record | {"aligned_labels": [event.label], "method": "exact"})
        elif targets := mapping.get(event.label):
            for i, target in enumerate(targets):
                event_id = event.event_id if i == 0 else f"{event.event_id}.{i + 1}"
                aligned.append(event.model_copy(update={"event_id": event_id, "label": target, "raw_label": event.label}))
            records.append(record | {"aligned_labels": targets, "method": "model"})
        else:
            aligned.append(event)
            records.append(record | {"aligned_labels": [], "method": "unmatched"})
    return observation.model_copy(update={"events": aligned}), records
