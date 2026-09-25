import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from praxiproof.constraints.schema import Constraint, ConstraintType

_ORDERING = {ConstraintType.BEFORE: 1, ConstraintType.PRECONDITION: 1, ConstraintType.AFTER: -1}
from praxiproof.document.extract import Block, ExtractedDocument
from praxiproof.ir.evidence import Evidence
from praxiproof.ir.requirement import EventDef, Requirement, RequirementSet
from praxiproof.llm import LLM, LLMError

_NULLABLE_STRING = {"type": ["string", "null"]}

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "procedure": {"type": "string"},
        "sequence": {"type": "array", "items": {"type": "string"}},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "description": {"type": "string"}},
                "required": ["label", "description"],
            },
        },
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "category": {"enum": ["safety", "procedure", "verification"]},
                    "severity": {"enum": ["critical", "major", "minor"]},
                    "observable": {"type": "boolean"},
                    "source_blocks": {"type": "array", "items": {"type": "integer"}},
                    "constraint": {
                        "type": "object",
                        "properties": {
                            "type": {"enum": [t.value for t in ConstraintType]},
                            "event": _NULLABLE_STRING,
                            "a": _NULLABLE_STRING,
                            "b": _NULLABLE_STRING,
                            "seconds": {"type": ["number", "null"]},
                            "min_count": {"type": ["integer", "null"]},
                        },
                        "required": ["type", "event", "a", "b", "seconds", "min_count"],
                    },
                },
                "required": ["statement", "category", "severity", "observable", "source_blocks", "constraint"],
            },
        },
    },
    "required": ["procedure", "sequence", "events", "requirements"],
}

REPAIR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"requirements": OUTPUT_SCHEMA["properties"]["requirements"]},
    "required": ["requirements"],
}

SYSTEM_PROMPT = f"""You compile maintenance and operating procedures into executable constraints that a
deterministic engine checks against events observed in a video of a technician doing the work.

Constraint DSL (fields not used by a type must be null):
{Constraint.__doc__}

Rules:
- Define a small vocabulary of events. Each event is one physical action or visible state change a camera
  filming the technician could capture (e.g. "fan_removed", "bezel_installed"). Labels are snake_case,
  past tense, specific to this procedure. Describe what the camera would show.
- Repeated identical steps (installing several identical fans or power supplies) share ONE event label,
  and the number required becomes a COUNT rule. Do not create numbered events such as psu_1_installed and
  psu_2_installed: a camera cannot tell which identical part is "first" or "second".
- When the manual offers alternatives ("any of the following", "or"), define ONE event covering all of them
  (e.g. "fan_health_confirmed: amber LED off, BMC sensors, or nvsm show fans checked") instead of one
  mandatory event per alternative. Mark it observable=false only if none of the alternatives is visible.
- Skip administrative steps that do not happen at the equipment: service tickets, ordering or receiving
  parts, packaging and shipping returns.
- sequence: list every event label once, in the order the manual has the technician perform them.
- Every requirement must come from the manual text. In source_blocks cite only the 1-3 numbered blocks that
  directly state it.
  Never invent limits, counts or steps that are not written.
- Explicit time limits become MAX_INTERVAL. Required steps become MUST_HAVE. Step order becomes BEFORE
  (or PRECONDITION when one step prepares for another). Checks performed after a step become AFTER.
- Direction matters:
  "Remove the bezel before removing the fan" -> BEFORE a=bezel_removed b=fan_removed
  "Unpack the new fan before you start" -> PRECONDITION a=new_fan_unpacked b=fan_removed
  "After installing the fan, confirm it is healthy" -> AFTER a=fan_health_confirmed b=fan_inserted
  "Replace the fan within 30 seconds" -> MAX_INTERVAL a=fan_removed b=fan_inserted seconds=30
  For AFTER, `a` is the later event and `b` the earlier one.
- observable is true by default. Hands-on actions (removing, inserting, pressing, unpacking, installing) and
  their timing and order are always observable. Set observable=false only when every way of satisfying the
  requirement happens on a screen, in software, by BMC, or otherwise off camera.
- category: safety for warnings about damage, overheating, electrical hazard or injury; verification for
  checks confirming the work succeeded; procedure otherwise.
- severity: critical for safety warnings and mandatory verification, major for required steps and ordering,
  minor for housekeeping.
"""


class RejectedItem(BaseModel):
    item: dict[str, Any]
    error: str


class CompileResult(BaseModel):
    requirement_set: RequirementSet
    evidence: list[Evidence]
    rejected: list[RejectedItem]
    blocks_used: int
    repaired: int = 0  # rules the model fixed itself after the validator rejected them


def select_blocks(doc: ExtractedDocument, procedure: str | None, max_chars: int = 20000) -> list[Block]:
    if sum(len(b.text) for b in doc.blocks) <= max_chars or not procedure:
        return _budget(doc.blocks, max_chars)
    keywords = {w for w in re.findall(r"[a-z0-9]+", procedure.lower()) if len(w) > 2}

    def score(block: Block) -> int:
        section = (block.section or "").lower()
        text = block.text.lower()
        return sum(2 * (k in section) + (k in text) for k in keywords)

    paged = [b for b in doc.blocks if b.page is not None]
    if paged:
        page_scores: dict[int, int] = {}
        for block in paged:
            page_scores[block.page] = page_scores.get(block.page, 0) + score(block)
        best = max(page_scores, key=lambda p: (page_scores[p], -p))
        chosen = [b for b in doc.blocks if b.page is not None and b.page >= best]
        return _budget(chosen, max_chars)
    return _budget([b for b in doc.blocks if score(b) > 0], max_chars)


def _budget(blocks: list[Block], max_chars: int) -> list[Block]:
    chosen, used = [], 0
    for block in blocks:
        if used + len(block.text) > max_chars:
            break
        chosen.append(block)
        used += len(block.text)
    return chosen


def _render(blocks: list[Block]) -> str:
    lines, section = [], None
    for block in blocks:
        if block.section != section:
            section = block.section
            lines.append(f"\n## {section or 'Untitled section'}")
        page = f" (p.{block.page})" if block.page is not None else ""
        lines.append(f"[B{block.index}]{page} {block.text}")
    return "\n".join(lines)


def compile_requirements(
    doc: ExtractedDocument, llm: LLM, model: str, procedure: str | None = None, max_chars: int = 20000
) -> CompileResult:
    blocks = select_blocks(doc, procedure, max_chars)
    if not blocks:
        raise ValueError("no manual text matched the requested procedure")
    focus = f'Compile only the procedure "{procedure}".' if procedure else "Compile the main procedure in this text."
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{focus}\n\nManual text:\n{_render(blocks)}"},
    ]
    raw = llm.chat_json(model, messages, OUTPUT_SCHEMA)
    allowed = {b.index for b in blocks}
    result = build_requirement_set(doc, raw, allowed, model)
    return _repair(doc, llm, model, messages, raw, allowed, result)


def _repair(
    doc: ExtractedDocument, llm: LLM, model: str, messages: list[dict[str, Any]], raw: dict[str, Any], allowed: set[int], first: CompileResult
) -> CompileResult:
    """Give the model one chance to fix the rules the validator rejected, quoting the exact error for each.

    Models slip on the strict constraint format (a field that must be null left filled in, a rule citing a block
    that does not exist) although they know what the rule should say. Only the rejected rules are re-asked and
    everything still goes through the same validator, so a repair can add rules but never bypass a check. If the
    call fails the first result stands.
    """
    broken = [r for r in first.rejected if "constraint" in r.item]  # rules; malformed event definitions are not repaired
    if not broken:
        return first
    listing = "\n".join(f"{i}. error: {r.error}\n   rule: {json.dumps(r.item, ensure_ascii=False)}" for i, r in enumerate(broken, 1))
    followup = messages + [
        {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
        {
            "role": "user",
            "content": (
                "The validator rejected these rules:\n" + listing + "\n\nReturn corrected versions of only these rules, "
                "following the constraint format exactly (fields a type does not use must be null; cite only block numbers "
                "that exist in the text; use only event labels you defined). Leave out any rule that cannot be expressed "
                "correctly instead of guessing."
            ),
        },
    ]
    try:
        fixed = llm.chat_json(model, followup, REPAIR_SCHEMA)
    except LLMError:
        return first
    candidates = fixed.get("requirements") or []
    bad = [r.item for r in first.rejected]
    kept = [item for item in raw.get("requirements", []) if item not in bad]
    second = build_requirement_set(doc, raw | {"requirements": kept + candidates}, allowed, model)
    if len(second.requirement_set.requirements) <= len(first.requirement_set.requirements):
        return first
    return second.model_copy(update={"repaired": len(second.requirement_set.requirements) - len(first.requirement_set.requirements)})


def build_requirement_set(doc: ExtractedDocument, raw: dict[str, Any], allowed_blocks: set[int], model: str | None) -> CompileResult:
    rejected: list[RejectedItem] = []
    events: dict[str, EventDef] = {}
    for item in raw.get("events", []):
        try:
            event = EventDef.model_validate(item)
        except ValidationError as exc:
            rejected.append(RejectedItem(item=item, error=_first_error(exc)))
            continue
        events.setdefault(event.label, event)

    position = {label: i for i, label in enumerate(dict.fromkeys(l for l in raw.get("sequence", []) if l in events))}
    requirements: list[Requirement] = []
    evidence: dict[str, Evidence] = {}
    seen_signatures: set[str] = set()
    for item in raw.get("requirements", []):
        try:
            constraint = Constraint.model_validate(item.get("constraint") or {})
        except ValidationError as exc:
            rejected.append(RejectedItem(item=item, error=_first_error(exc)))
            continue
        undefined = [e for e in constraint.events() if e not in events]
        if undefined:
            rejected.append(RejectedItem(item=item, error=f"undefined events: {undefined}"))
            continue
        if constraint.type in _ORDERING and constraint.a in position and constraint.b in position:
            direction = 1 if position[constraint.a] < position[constraint.b] else -1
            if direction != _ORDERING[constraint.type]:
                rejected.append(RejectedItem(item=item, error=f"{constraint.signature()} contradicts the step order {list(position)}"))
                continue
        sources = sorted({b for b in item.get("source_blocks", []) if b in allowed_blocks})
        if not sources:
            rejected.append(RejectedItem(item=item, error="no valid source block cited"))
            continue
        if constraint.signature() in seen_signatures:
            continue
        seen_signatures.add(constraint.signature())
        cited = [doc.evidence_for(b) for b in sources]
        evidence.update({e.evidence_id: e for e in cited})
        try:
            requirements.append(
                Requirement(
                    rule_id=f"R-{len(requirements) + 1:03d}",
                    statement=item["statement"],
                    constraint=constraint,
                    category=item["category"],
                    severity=item["severity"],
                    observable=item.get("observable", True),
                    evidence_ids=[e.evidence_id for e in cited],
                )
            )
        except (KeyError, ValidationError) as exc:
            rejected.append(RejectedItem(item=item, error=str(exc)[:300]))

    used_labels = {label for r in requirements for label in r.constraint.events()}
    ordered = sorted(events.values(), key=lambda e: position.get(e.label, len(position)))
    requirement_set = RequirementSet(
        source_id=doc.source_id,
        procedure=raw.get("procedure") or "Procedure",
        events=[e for e in ordered if e.label in used_labels],
        requirements=requirements,
        compiler_model=model,
    )
    return CompileResult(
        requirement_set=requirement_set,
        evidence=list(evidence.values()),
        rejected=rejected,
        blocks_used=len(allowed_blocks),
    )


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    return f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}"
