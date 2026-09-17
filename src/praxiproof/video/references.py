"""Reference images of each action, shown to the VLM next to the frames it has to label."""

import json
from dataclasses import dataclass
from pathlib import Path

from praxiproof.ir.requirement import EventDef
from praxiproof.verifier.aligner import Matcher

INDEX = "references.json"


@dataclass(frozen=True)
class ReferenceExample:
    label: str
    description: str
    images: tuple[bytes, ...]
    sources: tuple[str, ...] = ()


def load_references(directory: Path) -> list[ReferenceExample]:
    index = json.loads((directory / INDEX).read_text(encoding="utf-8"))
    return [
        ReferenceExample(
            label=entry["label"],
            description=entry["description"],
            images=tuple((directory / image["file"]).read_bytes() for image in entry["images"]),
            sources=tuple(image.get("source", image["file"]) for image in entry["images"]),
        )
        for entry in index["examples"]
    ]


def save_references(directory: Path, examples: list[ReferenceExample], note: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    entries = []
    for example in examples:
        images = []
        for i, (data, source) in enumerate(zip(example.images, example.sources)):
            name = f"{example.label}_{i + 1}.jpg"
            (directory / name).write_bytes(data)
            images.append({"file": name, "source": source})
        entries.append({"label": example.label, "description": example.description, "images": images})
    (directory / INDEX).write_text(json.dumps({"note": note, "examples": entries}, indent=2), encoding="utf-8")


def assign_references(
    examples: list[ReferenceExample], vocabulary: list[EventDef], matcher: Matcher | None
) -> list[tuple[str | None, ReferenceExample]]:
    """Pair each reference with the procedure step it shows; None means it shows none of the steps."""
    known = {e.label for e in vocabulary}
    pending = [EventDef.model_construct(label=x.label, description=x.description) for x in examples if x.label not in known]
    mapping = matcher(pending, vocabulary) if pending and matcher else {}
    pairs: list[tuple[str | None, ReferenceExample]] = []
    for example in examples:
        targets = [example.label] if example.label in known else mapping.get(example.label, [])
        # A reference that matches several steps would not tell them apart, so it only helps when it matches one.
        if len(targets) == 1:
            pairs.append((targets[0], example))
        elif not targets:
            pairs.append((None, example))
    return pairs
