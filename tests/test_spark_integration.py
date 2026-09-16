import pytest

from praxiproof.config import get_settings
from praxiproof.constraints.compiler import compile_requirements
from praxiproof.constraints.engine import evaluate
from praxiproof.demo import load_observation_fixture
from praxiproof.document.extract import extract
from praxiproof.ir.requirement import EventDef
from praxiproof.ir.verification import Status
from praxiproof.llm import OllamaClient
from praxiproof.verifier.aligner import align, llm_matcher
from praxiproof.video.local_vlm_adapter import LocalVLMBackend
from tests.conftest import DEMO_DIR

pytestmark = pytest.mark.spark


@pytest.fixture(scope="module")
def ollama():
    settings = get_settings()
    client = OllamaClient(settings.ollama_url, settings.keep_alive)
    available = client.ping()
    for model in (settings.llm_model, settings.vlm_model):
        if not any(m == model or m.split(":")[0] == model for m in available):
            pytest.skip(f"{model} not available in Ollama")
    return settings, client


@pytest.fixture(scope="module")
def compiled(ollama):
    settings, client = ollama
    doc = extract(DEMO_DIR / "manuals" / "dgx-h100-front-fan-replacement.html", "SPARK-HTML")
    return compile_requirements(doc, client, settings.llm_model, procedure="Front Fan Module Replacement")


def test_llm_compiles_timing_and_verification_rules(compiled):
    rs = compiled.requirement_set
    print("\n" + "\n".join(f"{r.rule_id} {r.constraint.signature()} {r.category}/{r.severity} observable={r.observable}" for r in rs.requirements))
    print("rejected:", [r.error for r in compiled.rejected])
    timing = [r for r in rs.requirements if r.constraint.type == "MAX_INTERVAL" and r.constraint.seconds == 30]
    assert timing, "expected a 30-second MAX_INTERVAL rule"
    assert timing[0].category == "safety"
    cited = {e.evidence_id: e for e in compiled.evidence}
    assert any("30 seconds" in cited[e].text for e in timing[0].evidence_ids)
    for rule in rs.requirements:
        if rule.constraint.type == "AFTER":
            assert "insert" not in rule.constraint.a, f"{rule.rule_id} has AFTER reversed: {rule.constraint.signature()}"
    health_events = [e.label for e in rs.events if any(k in e.label for k in ("health", "verif", "confirm", "check", "led"))]
    assert any(
        r.constraint.type in ("MUST_HAVE", "AFTER") and set(r.constraint.events()) & set(health_events) for r in rs.requirements
    ), "expected a rule requiring the fan health check"


@pytest.mark.parametrize(("name", "expected"), [("fan_replacement_A", Status.PASS), ("fan_replacement_C", Status.VIOLATION)])
def test_demo_observation_aligns_to_llm_vocabulary(ollama, compiled, name, expected):
    settings, client = ollama
    rs = compiled.requirement_set
    _, observation = load_observation_fixture(DEMO_DIR / "observations" / f"{name}.json")
    aligned, records = align(observation, rs.events, llm_matcher(client, settings.llm_model))
    print("\n" + "\n".join(f"{r['observed_label']} -> {r['aligned_labels']} ({r['method']})" for r in records))
    labels = {r["observed_label"]: set(r["aligned_labels"]) for r in records}
    assert not labels["new_fan_unpacked"] & (labels["fan_removed"] | labels["fan_inserted"])
    verdicts = evaluate(rs, aligned)
    for v in verdicts:
        print(v.rule_id, v.constraint.signature(), v.status, v.reason)
    timing = [v for v in verdicts if v.constraint.type == "MAX_INTERVAL" and v.constraint.seconds == 30]
    assert timing and timing[0].status == expected


PDF_URL = "https://docs.nvidia.com/dgx/dgxh100-service-manual/dgxh100-service-manual.pdf"


def test_pdf_manual_compiles_with_procedure_focus(ollama):
    settings, client = ollama
    pdf = DEMO_DIR / "manuals" / "dgxh100-service-manual.pdf"
    if not pdf.exists():
        pytest.skip(f"download the manual first: curl -Lo {pdf} {PDF_URL}")
    doc = extract(pdf, "SPARK-PDF", use_mineru=False)
    assert doc.page_count and doc.page_count > 50
    result = compile_requirements(doc, client, settings.llm_model, procedure="Front Fan Module Replacement")
    rs = result.requirement_set
    print("\n" + "\n".join(f"{r.rule_id} {r.constraint.signature()}" for r in rs.requirements))
    timing = [r for r in rs.requirements if r.constraint.type == "MAX_INTERVAL" and r.constraint.seconds == 30]
    assert timing
    cited = {e.evidence_id: e for e in result.evidence}
    assert all(cited[e].locator.page for e in timing[0].evidence_ids)


def test_vlm_backend_runs_on_real_video(ollama, make_video):
    settings, client = ollama
    video = make_video(12)
    rs_events = [EventDef(label="fan_removed", description="A server fan module is pulled out of its bay")]
    observation, evidence = LocalVLMBackend(client, settings.vlm_model).observe(video, "SPARK-VID", rs_events, "fan replacement")
    print("\nobserved:", [(e.label, e.start, e.end, e.confidence) for e in observation.events])
    assert observation.duration == pytest.approx(12, abs=0.5)
    assert len(evidence) == len(observation.events)
