import pytest
from fastapi.testclient import TestClient

from praxiproof.api.app import create_app
from praxiproof.ir.evidence import Evidence, VideoLocator
from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.runtime.rca_agent import RCAAgent
from tests.conftest import DEMO_DIR, FakeLLM, reference_as_llm_output


class FakeBackend:
    name = "fake"

    def observe(self, path, source_id, vocabulary, procedure):
        events = [
            ObservedEvent(event_id="O-001", label="fan_removed", start=10, end=14, time_uncertainty=0.5, confidence=0.9, evidence_id=f"EV-{source_id}-O001"),
            ObservedEvent(event_id="O-002", label="fan_inserted", start=50, end=55, time_uncertainty=0.5, confidence=0.9, evidence_id=f"EV-{source_id}-O002"),
        ]
        evidence = [
            Evidence(evidence_id=e.evidence_id, source_type="video", source_id=source_id, sha256="0" * 64,
                     locator=VideoLocator(start=e.start, end=e.end), text=e.label, extractor="fake", confidence=0.9)
            for e in events
        ]
        return Observation(source_id=source_id, duration=20, backend="fake", events=events), evidence


@pytest.fixture
def client(settings, reference):
    fake = FakeLLM(json_handler=lambda *_: reference_as_llm_output(reference))
    app = create_app(settings, llm=fake, backend_factory=FakeBackend, demo_dir=DEMO_DIR)
    with TestClient(app) as c:
        c.fake = fake
        yield c


def _run(client) -> str:
    html = (DEMO_DIR / "manuals" / "dgx-h100-front-fan-replacement.html").read_bytes()
    manual = client.post("/api/manuals", files={"file": ("dgx-fan.html", html, "text/html")}, data={"procedure": "Front Fan Module Replacement"}).json()
    return client.post("/api/runs", json={"manual_id": manual["id"], "demo_observation": "fan_replacement_C"}).json()["id"]


def test_rca_agent_pass_shortcut_needs_no_llm_call(client):
    run_id = _run(client)
    core = client.app.state.core
    result = RCAAgent(core).analyze(run_id, "R-006")  # fan_health_verified rule, not the timing violation
    assert result["status"] == "ok"
    assert client.fake.chat_calls == []


def test_rca_agent_uses_raw_tools_and_parses_rca_result(client):
    run_id = _run(client)
    core = client.app.state.core
    client.fake.chat_replies = [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_verdict_detail", "arguments": {}}}]},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_raw_observation", "arguments": {}}}]},
        {
            "role": "assistant",
            "content": 'RCA_RESULT:\n{"category": "GENUINE_VIOLATION", "confidence": "high", '
            '"explanation": "both events are seen well past 30s apart", "recommendation": "retrain the technician"}',
        },
    ]

    result = RCAAgent(core).analyze(run_id, "R-003")

    assert result == {
        "status": "ok",
        "category": "GENUINE_VIOLATION",
        "confidence": "high",
        "explanation": "both events are seen well past 30s apart",
        "recommendation": "retrain the technician",
        "trace": [{"tool": "get_verdict_detail", "arguments": {}}, {"tool": "get_raw_observation", "arguments": {}}],
    }
    tool_messages = [m for m in client.fake.chat_calls[-1] if m.get("role") == "tool"]
    assert "reason_code" in tool_messages[0]["content"]
    assert "raw_label" in tool_messages[1]["content"] and "time_uncertainty" in tool_messages[1]["content"]


def test_rca_agent_reports_failure_without_rca_result_block(client):
    run_id = _run(client)
    core = client.app.state.core
    client.fake.chat_replies = [{"role": "assistant", "content": "I think it's probably fine."}]

    result = RCAAgent(core).analyze(run_id, "R-003")

    assert result["status"] == "failed" and "RCA_RESULT" in result["error"]


def test_compliance_agent_delegates_to_rca(client):
    run_id = _run(client)
    client.fake.chat_replies = [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_verification_report", "arguments": {"run_id": run_id}}}]},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "run_root_cause_analysis", "arguments": {"run_id": run_id, "rule_id": "R-003"}}}]},
        {"role": "assistant", "content": 'RCA_RESULT:\n{"category": "GENUINE_VIOLATION", "confidence": "high", "explanation": "e", "recommendation": "r"}'},
        {"role": "assistant", "content": "R-003 failed because the fan swap genuinely took too long (GENUINE_VIOLATION)."},
    ]

    r = client.post("/api/agent/ask", json={"question": "Why did R-003 fail?", "run_id": run_id}).json()

    assert [t["tool"] for t in r["tool_calls"]] == ["get_verification_report", "run_root_cause_analysis"]
    assert "GENUINE_VIOLATION" in r["answer"]
    rca_tool_result = [m for m in client.fake.chat_calls[-1] if m.get("role") == "tool"][-1]["content"]
    assert '"category": "GENUINE_VIOLATION"' in rca_tool_result


def test_compliance_trace_embeds_the_rca_agents_own_tool_calls(client):
    run_id = _run(client)
    client.fake.chat_replies = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "run_root_cause_analysis", "arguments": {"run_id": run_id, "rule_id": "R-003"}}}]},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c2", "function": {"name": "get_raw_observation", "arguments": {}}}]},
        {"role": "assistant", "content": 'RCA_RESULT:\n{"category": "GENUINE_VIOLATION", "confidence": "high", "explanation": "e", "recommendation": "r"}'},
        {"role": "assistant", "content": "done"},
    ]

    trace = client.post("/api/agent/ask", json={"question": "why?", "run_id": run_id}).json()["tool_calls"]

    assert trace[0]["agent"] == "rca"
    assert [s["tool"] for s in trace[0]["sub_trace"]] == ["get_raw_observation"]
    assert trace[0]["result"]["category"] == "GENUINE_VIOLATION" and "trace" not in trace[0]["result"]
    seen_by_model = [m for m in client.fake.chat_calls[-1] if m.get("role") == "tool"][-1]
    assert "sub_trace" not in seen_by_model["content"] and seen_by_model["tool_call_id"] == "c1"


def test_analyze_endpoint_runs_the_rca_agent_for_one_rule(client):
    run_id = _run(client)
    client.fake.chat_replies = [
        {"role": "assistant", "content": 'RCA_RESULT:\n{"category": "GENUINE_VIOLATION", "confidence": "medium", "explanation": "e", "recommendation": "r"}'}
    ]
    r = client.post(f"/api/runs/{run_id}/verdicts/R-003/analyze")
    assert r.status_code == 200 and r.json()["category"] == "GENUINE_VIOLATION" and r.json()["trace"] == []
    assert client.post(f"/api/runs/{run_id}/verdicts/R-999/analyze").status_code == 404


def test_evaluation_endpoint_reports_the_measured_results(client):
    data = client.get("/api/evaluation").json()
    shipped = next(b for b in data["backends"] if b["shipped"])
    assert (shipped["id"], shipped["f1"]) == ("ddm_vlm_tuned", 0.971)
    assert data["baseline"]["violating"] == {"n": 4, "praxiproof_correct": 4, "samples": 12, "baseline_correct": 4, "baseline_false_compliant": 6}
    assert data["baseline"]["compliant"]["praxiproof_cleared"] == 0
    assert [a["id"] for a in data["agents"]] == ["compliance", "rca"] and "run_root_cause_analysis" in data["agents"][0]["tools"]
    assert data["vlm_selection"][0]["model"] == "gemma4:31b"


@pytest.mark.parametrize(
    "reply",
    [
        'RCA_RESULT:\n{"category": "LOW_CONFIDENCE", "confidence": "high", "explanation": "e", "recommendation": "r"}',
        '```json\n{\n  "category": "LOW_CONFIDENCE",\n  "confidence": "high",\n  "explanation": "e",\n  "recommendation": "r"\n}\n```',
        'Here is my analysis: {"note": "ignore"} and the result {"category": "LOW_CONFIDENCE", "confidence": "high", "explanation": "e", "recommendation": "r"}',
    ],
)
def test_rca_result_parsing_tolerates_how_real_models_format_it(client, reply):
    run_id = _run(client)
    client.fake.chat_replies = [{"role": "assistant", "content": reply}]
    result = RCAAgent(client.app.state.core).analyze(run_id, "R-003")
    assert result["status"] == "ok" and result["category"] == "LOW_CONFIDENCE" and result["explanation"] == "e"


def test_rca_result_with_an_unknown_category_is_rejected(client):
    run_id = _run(client)
    client.fake.chat_replies = [{"role": "assistant", "content": '{"category": "MAYBE_BAD_LUCK", "explanation": "e"}'}]
    assert RCAAgent(client.app.state.core).analyze(run_id, "R-003")["status"] == "failed"
