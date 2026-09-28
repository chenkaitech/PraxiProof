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
    demos = client.get("/api/demo/observations").json()
    assert {o["name"] for o in demos} == {
        "fan_replacement_A", "fan_replacement_B", "fan_replacement_C",
        "cover_install_A", "cover_install_B", "cover_install_C",
    }
    assert all(o["title_zh"] for o in demos)

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
    assert finding["reason_code"] == "interval.violation"
    assert finding["reason_params"] == {"a": "fan_removed", "b": "fan_inserted", "limit": "30", "interval": "45.0", "uncertainty": "1.0"}
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


def test_pipeline_from_uploaded_manual_and_demo_observation(client):
    html = (DEMO_DIR / "manuals" / "dgx-h100-front-fan-replacement.html").read_bytes()
    r = client.post(
        "/api/pipelines",
        files={"manual": ("dgx-fan.html", html, "text/html")},
        data={"procedure": "Front Fan Module Replacement", "demo_observation": "fan_replacement_C"},
    )
    assert r.status_code == 202, r.text
    pipeline = client.get(f"/api/pipelines/{r.json()['id']}").json()
    assert pipeline["status"] == "done", pipeline.get("error")
    assert pipeline["manual"]["status"] == "ready" and pipeline["run"]["result"] == "Timing Violation"
    assert pipeline["result"] == "Timing Violation"

    skills = client.get("/api/skills").json()
    assert [s["id"] for s in skills] == [pipeline["skill_id"]] and skills[0]["review_status"] == "pending"
    approved = client.post(f"/api/skills/{pipeline['skill_id']}/approve").json()
    assert approved["review_status"] == "approved" and approved["reviewed_at"]


def test_pipeline_with_existing_manual_and_uploaded_video(client, make_video):
    manual = _upload_manual(client)
    r = client.post(
        "/api/pipelines",
        files={"video": ("fan.mp4", make_video(20).read_bytes(), "video/mp4")},
        data={"manual_id": manual["id"], "video_note": " edited: cover step removed "},
    )
    assert r.status_code == 202, r.text
    pipeline = client.get(f"/api/pipelines/{r.json()['id']}").json()
    assert pipeline["status"] == "done", pipeline.get("error")
    assert pipeline["video_id"] == "VID-001" and pipeline["run"]["result"] == "Timing Violation"
    assert client.get("/api/videos").json()[0]["note"] == "edited: cover step removed"
    assert client.get(f"/api/runs/{pipeline['run_id']}").json()["video_note"] == "edited: cover step removed"
    assert client.get("/api/pipelines").json()[0]["id"] == pipeline["id"]


def test_pipeline_validation(client):
    manual = _upload_manual(client)
    assert client.post("/api/pipelines", data={"demo_observation": "fan_replacement_A"}).status_code == 400
    assert client.post("/api/pipelines", data={"manual_id": manual["id"]}).status_code == 400
    both = client.post("/api/pipelines", data={"manual_id": manual["id"], "video_id": "VID-404", "demo_observation": "fan_replacement_A"})
    assert both.status_code == 400
    assert client.post("/api/pipelines", data={"manual_id": "MAN-404", "demo_observation": "fan_replacement_A"}).status_code == 404


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
    r = client.post("/api/agent/ask", json={"question": "是否遵守了 30 秒规则？", "run_id": run_id, "language": "zh"}).json()
    assert "Simplified Chinese" in client.fake.chat_calls[0][0]["content"]
    assert r["answer"].startswith("R-003 was violated")
    assert [t["tool"] for t in r["tool_calls"]] == ["get_verification_report", "search_manual"]
    tool_messages = [m for m in client.fake.chat_calls[-1] if m.get("role") == "tool"]
    assert "VIOLATION" in tool_messages[0]["content"]
    assert "01:12.1" in tool_messages[0]["content"] and "Replacing and Returning the Front Fan Module" in tool_messages[0]["content"]
    assert "within 30 seconds" in tool_messages[1]["content"]


def test_health_and_index(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["models"] == {"llm": True, "vlm": True}
    index = client.get("/")
    assert "PraxiProof" in index.text and index.headers["cache-control"] == "no-cache"
    assert '/static/js/router.js?v=' in index.text and '/static/i18n.js?v=' in index.text and '/static/styles.css?v=' in index.text
    assert client.get("/static/i18n.js").headers["cache-control"] == "no-cache"
    assert client.get("/static/js/router.js").status_code == 200


def test_manual_that_compiles_to_zero_rules_fails_instead_of_looking_ready(settings):
    empty = FakeLLM(json_handler=lambda *_: {"procedure": "P", "sequence": [], "events": [], "requirements": []})
    with TestClient(create_app(settings, llm=empty, backend_factory=FakeBackend, demo_dir=DEMO_DIR)) as c:
        html = (DEMO_DIR / "manuals" / "dgx-h100-front-fan-replacement.html").read_bytes()
        upload = c.post("/api/manuals", files={"file": ("fan.html", html, "text/html")}, data={"procedure": "Front Fan Module Replacement"})
        record = c.get(f"/api/manuals/{upload.json()['id']}").json()
        assert record["status"] == "failed"
        assert "no verifiable rules" in record["error"]


def test_manual_where_most_candidate_rules_were_invalid_fails_instead_of_looking_ready(settings):
    def rule(statement, event):
        return {"statement": statement, "category": "procedure", "severity": "major", "observable": True, "source_blocks": [1],
                "constraint": {"type": "MUST_HAVE", "event": event, "a": None, "b": None, "seconds": None, "min_count": None}}

    # one rule uses a defined event, three cite events the model never defined (what a truncated answer looks like)
    raw = {"procedure": "P", "sequence": ["fan_removed"], "events": [{"label": "fan_removed", "description": "d"}],
           "requirements": [rule("ok", "fan_removed"), rule("a", "x_one"), rule("b", "x_two"), rule("c", "x_three")]}
    with TestClient(create_app(settings, llm=FakeLLM(json_handler=lambda *_: raw), backend_factory=FakeBackend, demo_dir=DEMO_DIR)) as c:
        html = (DEMO_DIR / "manuals" / "dgx-h100-front-fan-replacement.html").read_bytes()
        upload = c.post("/api/manuals", files={"file": ("fan.html", html, "text/html")}, data={"procedure": "Front Fan Module Replacement"})
        record = c.get(f"/api/manuals/{upload.json()['id']}").json()
        assert record["status"] == "failed" and "only 1 of 4 candidate rules were valid" in record["error"]


def _client_with(settings, reference, **changes):
    from dataclasses import replace

    fake = FakeLLM(json_handler=lambda *_: reference_as_llm_output(reference))
    return TestClient(create_app(replace(settings, **changes), llm=fake, backend_factory=FakeBackend, demo_dir=DEMO_DIR))


def test_manual_upload_rejects_unsupported_types_and_oversize_files(client):
    r = client.post("/api/manuals", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400 and "unsupported file type .exe" in r.json()["detail"]
    r = client.post("/api/videos", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert r.status_code == 400 and ".mp4" in r.json()["detail"]
    assert client.get("/api/manuals").json() == [] and client.get("/api/videos").json() == []


def test_upload_larger_than_the_limit_is_refused_and_leaves_nothing_behind(settings, reference):
    with _client_with(settings, reference, max_upload_mb=1) as c:
        r = c.post("/api/videos", files={"file": ("big.mp4", b"0" * (1024 * 1024 + 1), "video/mp4")})
        assert r.status_code == 413 and "1 MB limit" in r.json()["detail"]
        assert list((settings.data_dir / "uploads").iterdir()) == []


def test_pipeline_with_a_bad_manual_stores_nothing(client):
    r = client.post(
        "/api/pipelines",
        files={"manual": ("m.docx", b"x", "application/octet-stream"), "video": ("v.mp4", b"x", "video/mp4")},
    )
    assert r.status_code == 400
    assert client.get("/api/videos").json() == [] and client.get("/api/manuals").json() == []


def test_api_token_protects_the_api_but_not_health_or_the_ui(settings, reference):
    with _client_with(settings, reference, api_token="s3cret") as c:
        assert c.get("/health").status_code == 200 and c.get("/").status_code == 200
        assert c.get("/api/auth").json() == {"required": True, "ok": False}
        assert c.get("/api/manuals").status_code == 401
        assert c.get("/api/manuals", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/api/manuals", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        assert c.get("/api/manuals", headers={"X-API-Token": "s3cret"}).status_code == 200
        c.cookies.set("pp_token", "s3cret")  # what the browser sends for <video>/<img> requests
        assert c.get("/api/manuals").status_code == 200 and c.get("/api/auth").json()["ok"] is True


def test_no_token_configured_means_open_access(client):
    assert client.get("/api/auth").json() == {"required": False, "ok": True}


def test_jobs_interrupted_by_a_restart_are_marked_failed(settings, reference):
    with _client_with(settings, reference) as first:
        core = first.app.state.core
        stuck = core.store.create("runs", {"status": "processing", "stage": "observing", "manual_id": "MAN-001", "video_id": None, "error": None})
        queued = core.store.create("manuals", {"filename": "a.html", "status": "queued", "error": None})
        done = core.store.create("runs", {"status": "done", "stage": None, "error": None})
    with _client_with(settings, reference) as second:
        core = second.app.state.core
        assert core.store.get("runs", stuck["id"])["status"] == "failed"
        assert "restart" in core.store.get("runs", stuck["id"])["error"]
        assert core.store.get("manuals", queued["id"])["status"] == "failed"
        assert core.store.get("runs", done["id"])["status"] == "done"


def test_stale_orphan_uploads_are_pruned_at_startup(settings, reference):
    import os
    import time

    uploads = settings.data_dir / "uploads"
    uploads.mkdir(parents=True)
    old, fresh = uploads / "old.mp4", uploads / "fresh.mp4"
    old.write_bytes(b"x"), fresh.write_bytes(b"x")
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    with _client_with(settings, reference):
        assert not old.exists() and fresh.exists()


def test_positive_int_environment_settings_are_validated(monkeypatch):
    from praxiproof.config import get_settings

    monkeypatch.setenv("PRAXIPROOF_MAX_UPLOAD_MB", "0")
    with pytest.raises(ValueError, match="PRAXIPROOF_MAX_UPLOAD_MB"):
        get_settings()
    monkeypatch.setenv("PRAXIPROOF_MAX_UPLOAD_MB", "512")
    monkeypatch.setenv("PRAXIPROOF_API_TOKEN", "tok")
    assert (get_settings().max_upload_mb, get_settings().api_token) == (512, "tok")


def test_frames_can_stay_local_while_the_text_model_is_remote(settings, reference):
    from dataclasses import replace

    from praxiproof.llm import OllamaClient, build_vlm

    remote = replace(settings, llm_provider="openai", openai_base_url="https://api.example.com/v1", vlm_provider="ollama")
    text, local = FakeLLM(json_handler=lambda *_: reference_as_llm_output(reference)), FakeLLM()
    client = TestClient(create_app(remote, llm=text, vlm=local, backend_factory=FakeBackend, demo_dir=DEMO_DIR))
    assert client.app.state.core.vlm is local and client.app.state.core.llm is text
    assert client.get("/api/settings").json()["data_flow"] == {"text": "api.example.com", "frames": "local"}
    # the default keeps everything on the one configured provider, as before
    same = TestClient(create_app(replace(remote, vlm_provider="same"), llm=text, backend_factory=FakeBackend, demo_dir=DEMO_DIR))
    assert same.get("/api/settings").json()["data_flow"] == {"text": "api.example.com", "frames": "api.example.com"}
    assert isinstance(build_vlm(remote, text), OllamaClient) and build_vlm(replace(remote, vlm_provider="same"), text) is text
    assert build_vlm(replace(settings, vlm_provider="ollama"), text) is text  # both local already: nothing to split


def test_backend_factory_gives_the_frame_client_to_the_video_backend(settings):
    from praxiproof.video.backend import get_backend

    text, vision = FakeLLM(), FakeLLM()
    assert get_backend(settings, text, vision).llm is vision
    assert get_backend(settings, text).llm is text


def test_a_hosted_text_model_name_is_not_checked_against_the_ollama_catalogue(settings):
    from praxiproof.config import validate_changes

    catalogue = [{"name": "gemma4:31b", "capabilities": ["completion", "vision"]}]
    assert validate_changes({"llm_model": "step-3.5-flash"}, catalogue, llm_in_models=False) == {"llm_model": "step-3.5-flash"}
    with pytest.raises(ValueError, match="not installed"):
        validate_changes({"vlm_model": "step-3.5-flash"}, catalogue, llm_in_models=False)  # frames still need a local vision model
    with pytest.raises(ValueError, match="not installed"):
        validate_changes({"llm_model": "step-3.5-flash"}, catalogue)
