import re

from praxiproof.ir.requirement import EventDef
from praxiproof.video.frames import probe
from praxiproof.video.local_vlm_adapter import LocalVLMBackend
from tests.conftest import FakeLLM

VOCAB = [
    EventDef(label="fan_removed", description="Failed fan module pulled out"),
    EventDef(label="fan_inserted", description="New fan module pushed in"),
]


def _frame_times(messages) -> list[float]:
    return [float(t) for t in re.findall(r"Frame \d+ at ([\d.]+)s", messages[-1]["content"])]


def test_probe(make_video):
    meta = probe(make_video(12))
    assert round(meta.duration) == 12
    assert (meta.width, meta.height, meta.fps) == (320, 240, 10.0)


def test_coarse_to_fine_observation(make_video):
    video = make_video(20)

    def handler(model, messages, schema, images):
        times = _frame_times(messages)
        assert images and len(images) == len(times)
        if "events" in schema["properties"]:
            hits = [i for i, t in enumerate(times, start=1) if 9.0 <= t <= 11.0]
            return {"events": [{"label": "fan_removed", "frame": hits[0], "confidence": 0.9}] if hits else []}
        first = next(i for i, t in enumerate(times, start=1) if t >= 9.0)
        last = next(i for i, t in enumerate(times, start=1) if t >= 11.0)
        return {"visible": True, "start_frame": first, "end_frame": last, "confidence": 0.8, "description": "fan pulled out"}

    fake = FakeLLM(json_handler=handler)
    observation, evidence = LocalVLMBackend(fake, "vlm").observe(video, "VID-001", VOCAB, "fan replacement")

    assert [e.label for e in observation.events] == ["fan_removed"]
    assert observation.approximate is True
    event = observation.events[0]
    assert 8.0 <= event.start <= 9.5 and 10.5 <= event.end <= 12.5
    assert event.confidence == 0.8 and event.time_uncertainty <= 0.5
    assert evidence[0].locator.frame_start == round(event.start * 10)
    assert evidence[0].source_id == "VID-001" and evidence[0].model == "vlm"
    assert {c["think"] for c in fake.json_calls} == {False}
    coarse_calls = [c for c in fake.json_calls if "events" in c["schema"]["properties"]]
    assert len(coarse_calls) == 4
    assert coarse_calls[0]["schema"]["properties"]["events"]["items"]["properties"]["label"]["enum"] == ["fan_removed", "fan_inserted"]


def test_unconfirmed_candidate_becomes_low_confidence(make_video):
    video = make_video(8)

    def handler(model, messages, schema, images):
        if "events" in schema["properties"]:
            return {"events": [{"label": "fan_inserted", "frame": 2, "confidence": 0.95}, {"label": "not_a_step", "frame": 1, "confidence": 1}]}
        return {"visible": False, "start_frame": None, "end_frame": None, "confidence": 0.1, "description": "nothing"}

    observation, _ = LocalVLMBackend(FakeLLM(json_handler=handler), "vlm").observe(video, "VID-002", VOCAB, "p")
    assert len(observation.events) == 1
    assert observation.events[0].label == "fan_inserted"
    assert observation.events[0].confidence <= 0.4


