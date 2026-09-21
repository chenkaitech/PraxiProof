import re

from praxiproof.ir.requirement import EventDef
from praxiproof.video.ddm_vlm_adapter import INFER_SCRIPT, DDMRunner, DDMVLMBackend
from praxiproof.video.references import ReferenceExample, assign_references, load_references, save_references
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

    labels = iter(lbl for _, _, lbl in truth for _ in range(2))  # two agreeing answers per segment

    def handler(model, messages, schema, images):
        assert len(images) == 8 and schema["properties"]["label"]["enum"] == ["fan_installed", "psu_installed", "none"]
        label = next(labels)
        return {"hands_working": label != "none", "part_handled": label, "label": label, "confidence": 0.9, "description": label}

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
    # Two agreeing answers settle a segment; frames are sampled at different offsets for each answer.
    assert len(fake.json_calls) == 10 and {c["think"] for c in fake.json_calls} == {False}
    assert all(e.confidence == 0.9 for e in observation.events)


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


def test_disagreeing_answers_make_a_low_confidence_label(make_video):
    video = make_video(10)
    answers = iter(["fan_installed", "psu_installed", "fan_installed"])
    fake = FakeLLM(json_handler=lambda *_: {"label": next(answers), "confidence": 0.9, "description": "d"})
    backend = DDMVLMBackend(fake, "vlm", FakeRunner([]), disagreement_confidence=0.25)
    observation, _ = backend.observe(video, "VID-3", VOCAB, "servers")
    assert [(e.label, e.confidence) for e in observation.events] == [("fan_installed", 0.25)]
    assert len(fake.json_calls) == 3


def test_a_step_beats_none_on_a_tie(make_video):
    video = make_video(10)
    answers = iter(["none", "psu_installed"])
    fake = FakeLLM(json_handler=lambda *_: {"label": next(answers), "confidence": 0.8, "description": "d"})
    observation, _ = DDMVLMBackend(fake, "vlm", FakeRunner([]), votes=2).observe(video, "VID-4", VOCAB, "servers")
    assert [(e.label, e.confidence) for e in observation.events] == [("psu_installed", 0.25)]


def test_reference_images_come_before_the_segment_frames(make_video):
    video = make_video(10)
    references = [
        ReferenceExample("fan", "a fan pressed in", (b"fan-1", b"fan-2")),
        ReferenceExample("other", "not a step", (b"other-1",)),
        ReferenceExample("part", "matches two steps", (b"part-1",)),
    ]
    matched = []

    def matcher(observed, vocabulary):
        matched.append([o.label for o in observed])
        return {"fan": ["fan_installed"], "other": [], "part": ["fan_installed", "psu_installed"]}

    fake = FakeLLM(json_handler=lambda *_: {"label": "fan_installed", "confidence": 0.9, "description": "d"})
    backend = DDMVLMBackend(fake, "vlm", FakeRunner([]), votes=1, references=references, matcher=matcher)
    observation, _ = backend.observe(video, "VID-5", VOCAB, "servers")

    call = fake.json_calls[0]
    assert call["images"][:3] == [b"fan-1", b"fan-2", b"other-1"] and len(call["images"]) == 11
    prompt = call["messages"][-1]["content"]
    assert "images 1-2: fan_installed: a fan pressed in" in prompt and "images 3-3: none (not a step)" in prompt and "part-1" not in prompt
    assert matched == [["fan", "other", "part"]] and observation.model == "ddm-net + vlm + 3 reference images"


def test_references_round_trip(tmp_path):
    examples = [ReferenceExample("fan", "a fan", (b"\xff\xd8a", b"\xff\xd8b"), ("Install_1 action 1", "Install_3 action 2"))]
    save_references(tmp_path / "refs", examples, note="test")
    assert load_references(tmp_path / "refs") == examples
    assert assign_references(examples, [EventDef(label="fan", description="x")], matcher=None) == [("fan", examples[0])]


def test_a_step_without_working_hands_is_none(make_video):
    video = make_video(10)
    fake = FakeLLM(json_handler=lambda *_: {"hands_working": False, "part_handled": "nothing", "label": "fan_installed", "confidence": 0.9, "description": "idle"})
    observation, _ = DDMVLMBackend(fake, "vlm", FakeRunner([])).observe(video, "VID-6", VOCAB, "servers")
    assert observation.events == []
    assert list(fake.json_calls[0]["schema"]["properties"])[:3] == ["hands_working", "part_handled", "label"]


def _two_segment_backend(fake, **kwargs):
    return DDMVLMBackend(fake, "vlm", FakeRunner([10.0]), disagreement_confidence=0.25, **kwargs)


def _first_pass_then(second_look):
    """First-pass answers: a confident fan segment and a segment the votes disagree on (-> weak). Then the second look."""
    first = iter(["fan_installed", "fan_installed", "psu_installed", "none", "psu_installed"])  # 2 agree | 3 disagree

    def handler(model, messages, schema, images):
        if "step_performed" in schema["properties"]:
            return second_look(images)
        label = next(first)
        return {"hands_working": label != "none", "part_handled": label, "label": label, "confidence": 0.9, "description": label}

    return FakeLLM(json_handler=handler)


def test_second_look_promotes_a_weak_event_the_majority_confirms(make_video):
    fake = _first_pass_then(lambda images: {"hands_working": True, "step_performed": True, "confidence": 0.95})
    observation, evidence = _two_segment_backend(fake, second_look_below=0.5).observe(make_video(20), "VID-4", VOCAB, "servers")

    by_label = {e.label: e for e in observation.events}
    assert by_label["fan_installed"].confidence == 0.9  # confident, never re-examined
    assert by_label["psu_installed"].confidence == 0.8  # promoted, capped below a first-pass agreement
    assert "second look: 2/2 votes confirm" in by_label["psu_installed"].description
    assert "second look" in next(e for e in evidence if e.text and "second look" in e.text).text
    looks = [c for c in fake.json_calls if "step_performed" in c["schema"]["properties"]]
    assert len(looks) == 2 and all(len(c["images"]) == 12 for c in looks)  # early stop once two votes agree


def test_second_look_that_is_not_confirmed_leaves_the_event_weak(make_video):
    fake = _first_pass_then(lambda images: {"hands_working": True, "step_performed": False, "confidence": 0.9})
    observation, _ = _two_segment_backend(fake, second_look_below=0.5).observe(make_video(20), "VID-5", VOCAB, "servers")
    weak = next(e for e in observation.events if e.label == "psu_installed")
    assert weak.confidence == 0.25 and "second look: 0/2 votes confirm" in weak.description


def test_second_look_is_off_by_default(make_video):
    fake = _first_pass_then(lambda images: {"hands_working": True, "step_performed": True, "confidence": 0.95})
    observation, _ = _two_segment_backend(fake).observe(make_video(20), "VID-6", VOCAB, "servers")
    assert next(e for e in observation.events if e.label == "psu_installed").confidence == 0.25
    assert not [c for c in fake.json_calls if "step_performed" in c["schema"]["properties"]]
