import pytest
from fastapi.testclient import TestClient

from praxiproof.api.app import create_app
from praxiproof.config import load_overrides, validate_changes
from praxiproof.llm import LLMError, OllamaClient
from praxiproof.service import PraxiProof
from tests.conftest import DEMO_DIR, FakeLLM

CATALOG = [
    {"name": "qwen3.6:35b-a3b-q8_0", "capabilities": ["completion", "vision", "tools", "thinking"], "parameter_size": "36.0B", "quantization": "Q8_0"},
    {"name": "qwen3:14b", "capabilities": ["completion", "tools"], "parameter_size": "14.8B", "quantization": "Q4_K_M"},
]


class CatalogLLM(FakeLLM):
    def models(self):
        return CATALOG

    def ping(self):
        return [m["name"] for m in CATALOG]


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, llm=CatalogLLM(), demo_dir=DEMO_DIR)) as c:
        yield c


def test_models_endpoint_lists_capabilities(client):
    assert client.get("/api/models").json() == CATALOG


def test_update_persists_and_applies(client, settings):
    r = client.put("/api/settings", json={"llm_model": "qwen3:14b", "vlm_model": "qwen3.6:35b-a3b-q8_0", "vlm_thinking": True, "min_confidence": 0.6})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["llm_model"], body["vlm_model"], body["vlm_thinking"], body["min_confidence"]) == ("qwen3:14b", "qwen3.6:35b-a3b-q8_0", True, 0.6)
    assert client.get("/api/settings").json()["llm_model"] == "qwen3:14b"
    assert client.get("/health").json()["models"] == {"llm": True, "vlm": True}

    reloaded = load_overrides(settings)
    assert (reloaded.llm_model, reloaded.vlm_model, reloaded.vlm_thinking, reloaded.min_confidence) == ("qwen3:14b", "qwen3.6:35b-a3b-q8_0", True, 0.6)
    with TestClient(create_app(settings, llm=CatalogLLM(), demo_dir=DEMO_DIR)) as fresh:
        assert fresh.get("/api/settings").json()["vlm_model"] == "qwen3.6:35b-a3b-q8_0"


@pytest.mark.parametrize(
    "body",
    [
        {"vlm_model": "qwen3:14b"},
        {"llm_model": "not-installed:1b"},
        {"video_backend": "cloud"},
        {"min_confidence": 1.5},
        {"video_backend": "nvidia_sop", "sop_bp_url": None},
        {"sop_bp_url": "ftp://blueprint"},
        {"vlm_thinking": "sometimes"},
    ],
)
def test_invalid_updates_are_rejected(client, body):
    before = client.get("/api/settings").json()
    assert client.put("/api/settings", json=body).status_code in (400, 422)
    assert client.get("/api/settings").json() == before


def test_blueprint_backend_needs_url(client):
    r = client.put("/api/settings", json={"video_backend": "nvidia_sop", "sop_bp_url": "http://127.0.0.1:8000/sop"})
    assert r.status_code == 200 and r.json()["sop_blueprint_configured"] is True


def test_ddm_backend_requires_existing_checkpoint(client, tmp_path):
    assert client.put("/api/settings", json={"video_backend": "ddm_vlm"}).status_code == 400
    assert client.put("/api/settings", json={"ddm_checkpoint": str(tmp_path / "missing.ckpt")}).status_code == 400
    checkpoint = tmp_path / "ddm.ckpt"
    checkpoint.write_bytes(b"weights")
    r = client.put("/api/settings", json={"video_backend": "ddm_vlm", "ddm_checkpoint": str(checkpoint)})
    assert r.status_code == 200 and r.json()["ddm_checkpoint"] == str(checkpoint)


def test_video_backend_uses_current_models(settings):
    core = PraxiProof(settings, CatalogLLM())
    assert core._backend_factory().model == settings.vlm_model
    assert core._backend_factory().thinking is False
    core.update_settings({"vlm_model": "qwen3.6:35b-a3b-q8_0", "vlm_thinking": True}, CATALOG)
    assert (core._backend_factory().model, core._backend_factory().thinking) == ("qwen3.6:35b-a3b-q8_0", True)
    core.update_settings({"video_backend": "nvidia_sop", "sop_bp_url": "http://127.0.0.1:8000/sop"}, None)
    assert core._backend_factory().name == "nvidia_sop"
    checkpoint = settings.data_dir / "ddm.ckpt"
    checkpoint.write_bytes(b"weights")
    core.update_settings({"video_backend": "ddm_vlm", "ddm_checkpoint": str(checkpoint)}, None)
    backend = core._backend_factory()
    assert (backend.name, backend.model, backend.runner.checkpoint) == ("ddm_vlm", "qwen3.6:35b-a3b-q8_0", checkpoint)


def test_model_catalog_skips_models_that_cannot_be_inspected(monkeypatch):
    client = OllamaClient("http://127.0.0.1:9")
    monkeypatch.setattr(client, "ping", lambda: ["qwen3:14b", "glm-5:cloud"])

    def show(path, payload):
        if payload["model"] == "glm-5:cloud":
            raise LLMError("Ollama /api/show returned 410: retired")
        return {"capabilities": ["completion"], "details": {"parameter_size": "14.8B", "quantization_level": "Q4_K_M", "family": "qwen3"}}

    monkeypatch.setattr(client, "_post", show)
    assert client.models() == [
        {"name": "qwen3:14b", "capabilities": ["completion"], "parameter_size": "14.8B", "quantization": "Q4_K_M", "family": "qwen3"}
    ]


def test_reference_dir_must_contain_an_index(tmp_path):
    with pytest.raises(ValueError, match="references.json"):
        validate_changes({"reference_dir": str(tmp_path)}, None)
    (tmp_path / "references.json").write_text("{}")
    assert validate_changes({"reference_dir": f" {tmp_path} "}, None) == {"reference_dir": str(tmp_path)}
    assert validate_changes({"reference_dir": ""}, None) == {"reference_dir": None}
