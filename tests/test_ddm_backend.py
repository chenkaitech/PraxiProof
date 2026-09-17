import re

from praxiproof.ir.requirement import EventDef
from praxiproof.video.ddm_vlm_adapter import INFER_SCRIPT, DDMRunner, DDMVLMBackend
from tests.conftest import FakeLLM

VOCAB = [
    EventDef(label="fan_installed", description="fan pressed into its slot"),
    EventDef(label="psu_installed", description="power supply seated"),
]


class FakeRunner:
    def __init__(self, boundaries):
        self._boundaries = boundaries
        self.calls = []

    def boundaries(self, video):
        self.calls.append(video)
        return self._boundaries


def test_segments_between_boundaries_are_labelled(make_video):
    video = make_video(20)
    truth = [(0, 3, "none"), (3, 7, "fan_installed"), (7, 12, "fan_installed"), (12.4, 18, "psu_installed"), (18, 20, "none")]

    def handler(model, messages, schema, images):
        start, end = map(float, re.search(r"from ([\d.]+)s to ([\d.]+)s", messages[-1]["content"]).groups())
        assert len(images) == 8 and schema["properties"]["label"]["enum"] == ["fan_installed", "psu_installed", "none"]
        label = next(lbl for s, e, lbl in truth if abs(s - start) < 0.01 and abs(e - end) < 0.2)
        return {"label": label, "confidence": 0.9, "description": label}

    fake = FakeLLM(json_handler=handler)
    runner = FakeRunner([3.0, 7.0, 12.0, 12.4, 18.0, 25.0])
    observation, evidence = DDMVLMBackend(fake, "vlm", runner).observe(video, "VID-1", VOCAB, "servers")

    assert [(e.label, e.start, e.end) for e in observation.events] == [
        ("fan_installed", 3.0, 7.0),
        ("fan_installed", 7.0, 12.0),
        ("psu_installed", 12.4, 18.0),
    ]
    assert observation.approximate and observation.model == "ddm-net + vlm"
    assert all(e.time_uncertainty == 0.5 for e in observation.events) and len(evidence) == 3
    assert len(fake.json_calls) == 5 and {c["think"] for c in fake.json_calls} == {False}


def test_unknown_label_is_treated_as_none(make_video):
    video = make_video(6)
    fake = FakeLLM(json_handler=lambda *_: {"label": "coffee_break", "confidence": "high", "description": "?"})
    observation, _ = DDMVLMBackend(fake, "vlm", FakeRunner([])).observe(video, "VID-2", VOCAB, "servers")
    assert observation.events == []


def test_runner_command_mounts_model_code_and_clip(tmp_path):
    checkpoint = tmp_path / "models" / "ddm.ckpt"
    runner = DDMRunner("praxiproof-ddm:26.08", "/opt/ddm/DDM-Net", str(checkpoint), tmp_path / "work")
    cmd = runner.command(tmp_path / "clips", "clip.mp4")
    assert cmd[:6] == ["docker", "run", "--rm", "--device", "nvidia.com/gpu=all", "--ipc=host"]
    assert f"{checkpoint.parent}:/workspace/ckpt:ro" in cmd and f"{INFER_SCRIPT}:/workspace/infer_ddm.py:ro" in cmd
    assert "praxiproof-ddm:26.08" in cmd and cmd[-1] == "/workspace/clips/clip.mp4"
    assert "/workspace/ckpt/ddm.ckpt" in cmd and INFER_SCRIPT.is_file()
