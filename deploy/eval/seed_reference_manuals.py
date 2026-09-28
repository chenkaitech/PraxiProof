"""Seed the two reference manuals (demo/requirements/*.json) into the live store, compiled deterministically
from the fixed JSON rather than by the LLM.

Why this exists: the "Demo observation (no video)" dropdown pairs a canned observation fixture with whatever
manual is currently in the database. If that manual was uploaded through the API, its ruleset was produced by a
live LLM compile, which is not guaranteed to reuse the exact event labels (e.g. "fan_inserted" vs "fan_installed")
the fixture was authored against; the alignment step can then legitimately fail to match them (it is deliberately
conservative about guessing), and a compliant fixture can come back as a violation. `praxiproof bench` and
BENCHMARK.md never hit this: they call `evaluate()` directly against `load_reference_requirements()`, bypassing
both the live database and the alignment step. This script gives the live dashboard the same guarantee, by
inserting a manual whose stored ruleset is exactly the reference JSON, once, so the Demo observation dropdown is
reliable for a live demo regardless of what else has been uploaded and recompiled in the meantime.

Usage (on the Spark): uv run python deploy/eval/seed_reference_manuals.py
"""
from pathlib import Path

from praxiproof.config import get_settings, load_overrides
from praxiproof.demo import load_reference_requirements
from praxiproof.service import _manual_counts
from praxiproof.store import Store

DEMO_DIR = Path.home() / "praxiproof/demo"
REFERENCES = [
    ("dgx-h100-front-fan.json", "dgx-h100-front-fan-replacement.html", "Front Fan Module Replacement (reference)"),
    ("server-fan-psu-cover.json", "server-fan-psu-cover-installation.md", "Server Fan, Power Supply and Cover Installation (reference)"),
]

settings = load_overrides(get_settings())
store = Store(settings.data_dir / "praxiproof.db")

for json_name, source_filename, display_name in REFERENCES:
    existing = [m for m in store.list("manuals", limit=1000) if m.get("filename") == display_name]
    if existing:
        print(f"already seeded: {existing[0]['id']} ({display_name})")
        continue
    rs, doc, evidence, _ = load_reference_requirements(DEMO_DIR / "requirements" / json_name, DEMO_DIR)
    record = store.create("manuals", {"filename": display_name, "procedure_hint": None, "status": "processing", "error": None})
    manual_id = record["id"]
    (settings.data_dir / "manuals").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "manuals" / f"{manual_id}.document.json").write_text(doc.model_dump_json(), encoding="utf-8")
    store.put_evidence(evidence)
    store.update(
        "manuals",
        manual_id,
        path=str(DEMO_DIR / "manuals" / source_filename),
        sha256=doc.sha256,
        page_count=doc.page_count,
        extractor=doc.extractor,
        status="ready",
        procedure=rs.procedure,
        requirement_set=rs.model_dump(mode="json"),
        rejected=[],
        repaired=0,
        blocks_used=len(doc.blocks),
        counts=_manual_counts(rs),
    )
    print(f"seeded: {manual_id} ({display_name}), {len(rs.requirements)} rules")
