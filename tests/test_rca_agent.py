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
