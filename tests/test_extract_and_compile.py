from pathlib import Path

import fitz
import pytest

from praxiproof.constraints.compiler import build_requirement_set, compile_requirements, select_blocks
from praxiproof.document.extract import blocks_from_mineru, extract
from tests.conftest import FakeLLM, reference_as_llm_output


def test_html_manual_extraction(demo_dir):
    doc = extract(demo_dir / "manuals" / "dgx-h100-front-fan-replacement.html", "M1")
    rule = next(b for b in doc.blocks if "within 30 seconds" in b.text)
    assert rule.section == "Replacing and Returning the Front Fan Module"
    assert doc.extractor == "html"
    assert doc.evidence_for(rule.index).citation() == "Replacing and Returning the Front Fan Module"
    assert len(doc.sha256) == 64


def test_markdown_extraction(tmp_path: Path):
    path = tmp_path / "sop.md"
    path.write_text("# Pump filter\n\nIntro line one\nline two\n\n1. Power off the pump\n- Wait 30 seconds\n\n► Check the gauge\n")
    doc = extract(path, "M2")
    assert [b.text for b in doc.blocks] == ["Pump filter", "Intro line one line two", "1. Power off the pump", "- Wait 30 seconds", "Check the gauge"]
    assert {b.section for b in doc.blocks} == {"Pump filter"}


def test_pdf_extraction_with_pages_and_sections(tmp_path: Path):
    path = tmp_path / "manual.pdf"
    pdf = fitz.open()
    for title, body in [("Safety", "Wear gloves at all times."), ("Fan Replacement", "Replace the fan within 30 seconds.")]:
        page = pdf.new_page()
        page.insert_text((72, 72), title, fontsize=20)
        page.insert_text((72, 120), body, fontsize=10)
    pdf.save(path)
    doc = extract(path, "M3", use_mineru=False)
    rule = next(b for b in doc.blocks if "30 seconds" in b.text)
    assert (rule.page, rule.section) == (2, "Fan Replacement")
    assert doc.page_count == 2
    assert doc.evidence_for(rule.index).citation() == "p.2"
    assert len(rule.bbox) == 4


def test_mineru_content_list_parsing():
    blocks = blocks_from_mineru(
        [
            {"type": "text", "text": "Fan Replacement", "text_level": 1, "page_idx": 37, "bbox": [1, 2, 3, 4]},
            {"type": "text", "text": "Replace within 30 seconds.", "page_idx": 37, "bbox": [1, 5, 3, 8]},
            {"type": "image", "img_path": "a.png", "page_idx": 37},
            {"type": "table", "table_body": "<table><tr><td>Fan</td></tr></table>", "page_idx": 38},
        ]
    )
    assert [(b.page, b.section) for b in blocks] == [(38, "Fan Replacement"), (38, "Fan Replacement"), (39, "Fan Replacement")]


def test_compile_uses_llm_output_and_links_evidence(demo_dir, reference):
    doc = reference[1]
    fake = FakeLLM(json_handler=lambda *_: reference_as_llm_output(reference))
    result = compile_requirements(doc, fake, "fake-llm", procedure="Front Fan Module Replacement")
    assert result.rejected == []
    rs = result.requirement_set
    assert [r.rule_id for r in rs.requirements] == [f"R-{i:03d}" for i in range(1, 9)]
    assert {r.constraint.signature() for r in rs.requirements} == {r.constraint.signature() for r in reference[0].requirements}
    evidence = {e.evidence_id: e for e in result.evidence}
    timing = next(r for r in rs.requirements if r.constraint.type == "MAX_INTERVAL")
    assert "30 seconds" in evidence[timing.evidence_ids[0]].text
    prompt = fake.json_calls[0]["messages"][1]["content"]
    assert "[B" in prompt and "Front Fan Module Replacement" in prompt


def test_compile_rejects_invalid_items(reference):
    doc = reference[1]
    raw = {
        "procedure": "p",
        "events": [{"label": "fan_removed", "description": "d"}, {"label": "fan_inserted", "description": "d"}, {"label": "Bad Label", "description": "d"}],
        "requirements": [
            {"statement": "ok", "category": "safety", "severity": "critical", "observable": True, "source_blocks": [1],
             "constraint": {"type": "MAX_INTERVAL", "event": None, "a": "fan_removed", "b": "fan_inserted", "seconds": 30, "min_count": None}},
            {"statement": "dup", "category": "safety", "severity": "critical", "observable": True, "source_blocks": [2],
             "constraint": {"type": "MAX_INTERVAL", "event": None, "a": "fan_removed", "b": "fan_inserted", "seconds": 30, "min_count": None}},
            {"statement": "undefined", "category": "procedure", "severity": "major", "observable": True, "source_blocks": [1],
             "constraint": {"type": "MUST_HAVE", "event": "bezel_removed", "a": None, "b": None, "seconds": None, "min_count": None}},
            {"statement": "uncited", "category": "procedure", "severity": "major", "observable": True, "source_blocks": [9999],
             "constraint": {"type": "MUST_HAVE", "event": "fan_removed", "a": None, "b": None, "seconds": None, "min_count": None}},
            {"statement": "bad dsl", "category": "procedure", "severity": "major", "observable": True, "source_blocks": [1],
             "constraint": {"type": "BEFORE", "event": "fan_removed", "a": None, "b": None, "seconds": None, "min_count": None}},
        ],
    }
    result = build_requirement_set(doc, raw, {1, 2}, "fake")
    assert len(result.requirement_set.requirements) == 1
    assert len(result.rejected) == 4
    assert {e.label for e in result.requirement_set.events} == {"fan_removed", "fan_inserted"}


def test_compile_rejects_ordering_that_contradicts_sequence(reference):
    doc = reference[1]

    def item(kind, a, b):
        return {
            "statement": f"{kind} {a} {b}", "category": "procedure", "severity": "major", "observable": True, "source_blocks": [1],
            "constraint": {"type": kind, "event": None, "a": a, "b": b, "seconds": None, "min_count": None},
        }

    raw = {
        "procedure": "p",
        "sequence": ["fan_inserted", "health_checked", "bezel_installed"],
        "events": [{"label": l, "description": l} for l in ("bezel_installed", "fan_inserted", "health_checked")],
        "requirements": [
            item("BEFORE", "health_checked", "bezel_installed"),
            item("BEFORE", "bezel_installed", "health_checked"),
            item("AFTER", "health_checked", "fan_inserted"),
            item("AFTER", "fan_inserted", "health_checked"),
            item("PRECONDITION", "fan_inserted", "health_checked"),
        ],
    }
    result = build_requirement_set(doc, raw, {1}, "fake")
    kept = [r.constraint.signature() for r in result.requirement_set.requirements]
    assert kept == ["BEFORE(health_checked,bezel_installed)", "AFTER(health_checked,fan_inserted)", "PRECONDITION(fan_inserted,health_checked)"]
    assert all("contradicts the step order" in r.error for r in result.rejected)
    assert [e.label for e in result.requirement_set.events] == ["fan_inserted", "health_checked", "bezel_installed"]


def test_select_blocks_focuses_on_procedure_pages(tmp_path: Path):
    path = tmp_path / "long.pdf"
    pdf = fitz.open()
    for i in range(30):
        page = pdf.new_page()
        text = "Front fan module replacement: replace within 30 seconds." if i == 20 else f"Unrelated chapter {i} " * 40
        page.insert_text((72, 72), text[:90], fontsize=10)
        for line in range(20):
            page.insert_text((72, 100 + line * 12), (f"filler {i} " * 12)[:90], fontsize=10)
    pdf.save(path)
    doc = extract(path, "M4", use_mineru=False)
    chosen = select_blocks(doc, "Front Fan Module Replacement", max_chars=3000)
    assert chosen and chosen[0].page == 21


def test_compile_raises_when_nothing_selected(reference):
    doc = reference[1].model_copy(update={"blocks": []})
    with pytest.raises(ValueError):
        compile_requirements(doc, FakeLLM(), "fake", procedure="x")
