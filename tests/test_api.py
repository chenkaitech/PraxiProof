import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from praxiproof.api.app import create_app
from praxiproof.ir.evidence import Evidence, VideoLocator
from praxiproof.ir.observation import Observation, ObservedEvent
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


def _upload_manual(client) -> dict:
    html = (DEMO_DIR / "manuals" / "dgx-h100-front-fan-replacement.html").read_bytes()
    r = client.post("/api/manuals", files={"file": ("dgx-fan.html", html, "text/html")}, data={"procedure": "Front Fan Module Replacement"})
    assert r.status_code == 202
    manual = client.get(f"/api/manuals/{r.json()['id']}").json()
    assert manual["status"] == "ready", manual.get("error")
    return manual


def test_manual_upload_compiles_rules(client):
    manual = _upload_manual(client)
    assert manual["id"] == "MAN-001"
    assert manual["counts"] == {"rules": 8, "safety_rules": 1, "steps": 8, "critical": 2}
    timing = next(r for r in manual["requirement_set"]["requirements"] if r["constraint"]["type"] == "MAX_INTERVAL")
    assert "30 seconds" in manual["evidence"][timing["evidence_ids"][0]]["text"]


def test_demo_run_review_skill_and_dashboard(client):
    manual = _upload_manual(client)
    assert {o["name"] for o in client.get("/api/demo/observations").json()} == {"fan_replacement_A", "fan_replacement_B", "fan_replacement_C"}

    r = client.post("/api/runs", json={"manual_id": manual["id"], "demo_observation": "fan_replacement_C"})
    assert r.status_code == 202
    run = client.get(f"/api/runs/{r.json()['id']}").json()
    assert run["status"] == "done", run.get("error")
    assert (run["result"], run["violations"]) == ("Timing Violation", 1)
    assert run["metrics"]["evidence_traceability"]["value"] == 1.0
    assert run["metrics"]["safety_coverage"] == {"value": 1.0, "numerator": 1, "denominator": 1}
    finding = run["findings"][0]
    assert finding["kind"] == "Timing Violation" and finding["measured"]["observed_seconds"] == 45.0
    assert "30 seconds" in finding["manual"][0]["text"]
    assert finding["video"][0]["start"] == 72.1

    reviewed = client.post(f"/api/runs/{run['id']}/verdicts/{finding['rule_id']}/review", json={"decision": "rejected"}).json()
    assert (reviewed["result"], reviewed["violations"]) == ("PASS", 0)
    client.post(f"/api/runs/{run['id']}/verdicts/{finding['rule_id']}/review", json={"decision": None})

    skill = client.post(f"/api/runs/{run['id']}/skill").json()
    assert skill["name"] == "dgx-h100-front-fan-module-replacement"
    assert client.get(f"/api/skills/{skill['id']}/skill.md").text.startswith("---\nname: dgx-h100-front-fan-module-replacement")
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/skills/{skill['id']}/download").content))
    assert f"{skill['name']}/SKILL.md" in archive.namelist()

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["latest_run"]["id"] == run["id"]
    assert dashboard["findings"][0]["rule_id"] == finding["rule_id"]
    assert dashboard["latest_manual"]["counts"]["rules"] == 8


def test_video_run_uses_backend(client, make_video):
    manual = _upload_manual(client)
    video = client.post("/api/videos", files={"file": ("fan.mp4", make_video(20).read_bytes(), "video/mp4")}).json()
    assert video["meta"]["width"] == 320
    assert client.get(f"/api/videos/{video['id']}/frame", params={"t": 1}).headers["content-type"] == "image/jpeg"

    run_id = client.post("/api/runs", json={"manual_id": manual["id"], "video_id": video["id"]}).json()["id"]
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "done", run.get("error")
    assert run["result"] == "Timing Violation"
    assert run["findings"][0]["video"][0]["start"] == 10


def test_missing_step_result(client):
    manual = _upload_manual(client)
    run_id = client.post("/api/runs", json={"manual_id": manual["id"], "demo_observation": "fan_replacement_B"}).json()["id"]
    run = client.get(f"/api/runs/{run_id}").json()
    assert (run["result"], run["violations"]) == ("Missing Step", 2)
    assert {f["kind"] for f in run["findings"]} == {"Missing Step"}


def test_invalid_requests(client):
    assert client.post("/api/videos", files={"file": ("x.mp4", b"not a video", "video/mp4")}).status_code == 400
    assert client.get("/api/runs/V-999").status_code == 404
    manual = _upload_manual(client)
    assert client.post("/api/runs", json={"manual_id": manual["id"]}).status_code == 400
    assert client.post("/api/runs", json={"manual_id": manual["id"], "demo_observation": "../../etc/passwd"}).status_code == 404


def test_agent_uses_tools(client):
    manual = _upload_manual(client)
    run_id = client.post("/api/runs", json={"manual_id": manual["id"], "demo_observation": "fan_replacement_C"}).json()["id"]
    client.fake.chat_replies = [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_verification_report", "arguments": {"run_id": run_id}}}]},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "search_manual", "arguments": {"manual_id": manual["id"], "query": "30 seconds overheating"}}}]},
        {"role": "assistant", "content": "R-003 was violated: 45.0s observed vs 30s allowed."},
    ]
    r = client.post("/api/agent/ask", json={"question": "Was the 30 second rule respected?", "run_id": run_id}).json()
    assert r["answer"].startswith("R-003 was violated")
    assert [t["tool"] for t in r["tool_calls"]] == ["get_verification_report", "search_manual"]
    tool_messages = [m for m in client.fake.chat_calls[-1] if m.get("role") == "tool"]
    assert "VIOLATION" in tool_messages[0]["content"]
    assert "within 30 seconds" in tool_messages[1]["content"]


def test_health_and_index(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["models"] == {"llm": True, "vlm": True}
    assert "PraxiProof" in client.get("/").text
