import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from praxiproof.config import Settings
from praxiproof.demo import load_observation_fixture, load_reference_requirements

DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"


class FakeLLM:
    def __init__(
        self,
        json_handler: Callable[[str, list[dict], dict, list[bytes] | None], dict] | None = None,
        chat_replies: list[dict] | None = None,
    ):
        self.json_handler = json_handler
        self.chat_replies = list(chat_replies or [])
        self.json_calls: list[dict[str, Any]] = []
        self.chat_calls: list[list[dict]] = []

    def chat_json(self, model, messages, schema, images=None, think=None):
        self.json_calls.append({"model": model, "messages": messages, "schema": schema, "images": images, "think": think})
        return self.json_handler(model, messages, schema, images)

    def chat(self, model, messages, tools=None):
        self.chat_calls.append([dict(m) for m in messages])
        return self.chat_replies.pop(0)


@pytest.fixture
def demo_dir() -> Path:
    return DEMO_DIR


@pytest.fixture
def reference():
    return load_reference_requirements(DEMO_DIR / "requirements" / "dgx-h100-front-fan.json", DEMO_DIR)


@pytest.fixture
def observation_fixture():
    def load(name: str):
        return load_observation_fixture(DEMO_DIR / "observations" / f"{name}.json")

    return load


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        ollama_url="http://127.0.0.1:9",
        llm_model="fake-llm",
        vlm_model="fake-vlm",
        vlm_thinking=False,
        video_backend="local_vlm",
        sop_bp_url=None,
        data_dir=tmp_path / "data",
        keep_alive="1m",
        min_confidence=0.5,
    )


def reference_as_llm_output(reference) -> dict[str, Any]:
    requirement_set, doc, evidence, _ = reference
    by_id = {e.evidence_id: e for e in evidence}
    return {
        "procedure": requirement_set.procedure,
        "sequence": [e.label for e in requirement_set.events],
        "events": [e.model_dump() for e in requirement_set.events],
        "requirements": [
            {
                "statement": r.statement,
                "category": r.category,
                "severity": r.severity,
                "observable": r.observable,
                "source_blocks": [by_id[e].locator.block_index for e in r.evidence_ids],
                "constraint": r.constraint.model_dump(mode="json"),
            }
            for r in requirement_set.requirements
        ],
    }


@pytest.fixture
def make_video(tmp_path: Path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")

    def make(seconds: int = 20, name: str = "clip.mp4") -> Path:
        path = tmp_path / name
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=10", "-pix_fmt", "yuv420p", str(path)],
            check=True,
        )
        return path

    return make


def dumps(data: Any) -> str:
    return json.dumps(data)
