import json
from pathlib import Path
from typing import Any

from praxiproof.document.extract import ExtractedDocument, extract
from praxiproof.ir.evidence import Evidence
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import EventDef, Requirement, RequirementSet


def load_reference_requirements(path: Path, demo_dir: Path) -> tuple[RequirementSet, ExtractedDocument, list[Evidence], dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    doc = extract(demo_dir / data["manual_file"], source_id="DEMO-MANUAL")
    evidence: dict[str, Evidence] = {}
    requirements, quotes = [], {}
    for item in data["requirements"]:
        block = next((b for b in doc.blocks if item["quote"].lower() in b.text.lower()), None)
        if block is None:
            raise ValueError(f"{item['rule_id']}: quote not found in manual: {item['quote']!r}")
        cited = doc.evidence_for(block.index)
        evidence[cited.evidence_id] = cited
        quotes[item["rule_id"]] = item["quote"]
        fields = {k: v for k, v in item.items() if k != "quote"}
        requirements.append(Requirement.model_validate(fields | {"evidence_ids": [cited.evidence_id]}))
    requirement_set = RequirementSet(
        source_id=doc.source_id,
        procedure=data["procedure"],
        events=[EventDef.model_validate(e) for e in data["events"]],
        requirements=requirements,
        compiler_model="reference",
    )
    return requirement_set, doc, list(evidence.values()), quotes


def load_observation_fixture(path: Path) -> tuple[dict[str, Any], Observation]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, Observation.model_validate(data["observation"])
