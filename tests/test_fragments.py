from praxiproof.ir.requirement import EventDef
from praxiproof.video.ddm_vlm_adapter import DDMVLMBackend
from praxiproof.video.fragments import merge_fragments
from praxiproof.video.normalizer import RawSegment
from praxiproof.video.references import ReferenceExample, load_references, save_references
from tests.conftest import FakeLLM
from tests.test_ddm_backend import FakeRunner

TYPICAL = {"psu": 7.0, "fan": 7.5}


def seg(label, start, end, confidence=0.9, description=""):
    return RawSegment(label=label, start=start, end=end, confidence=confidence, description=description)


def test_two_pieces_of_one_action_become_one_event():
    out = merge_fragments([seg("psu", 50, 54), seg("psu", 54, 57.5)], TYPICAL)
    assert [(s.label, s.start, s.end) for s in out] == [("psu", 50, 57.5)]
    assert "merged 2 fragments" in out[0].description


def test_two_separate_actions_are_never_fused():
    # 7 s + 7 s back to back is two installations, far longer than one takes
    out = merge_fragments([seg("psu", 50, 57), seg("psu", 57, 64)], TYPICAL)
    assert [(s.start, s.end) for s in out] == [(50, 57), (57, 64)]


def test_only_touching_segments_of_the_same_label_merge():
    assert len(merge_fragments([seg("psu", 50, 53), seg("fan", 53, 56)], TYPICAL)) == 2
    assert len(merge_fragments([seg("psu", 50, 53), seg("psu", 56, 59)], TYPICAL)) == 2  # a 3 s gap is not touching
    assert len(merge_fragments([seg("psu", 56, 59), seg("psu", 50, 53)], TYPICAL)) == 2  # order does not matter, only time


def test_unknown_duration_leaves_the_segments_alone():
    assert len(merge_fragments([seg("cover", 0, 2), seg("cover", 2, 4)], TYPICAL)) == 2


def test_the_confident_piece_decides_confidence_and_description():
    out = merge_fragments([seg("psu", 50, 52, 0.25, "weak"), seg("psu", 52, 56, 0.9, "strong")], TYPICAL)
    assert (out[0].confidence, out[0].description.startswith("strong")) == (0.9, True)


def test_tolerance_controls_how_generous_the_merge_is():
    pieces = [seg("psu", 50, 54), seg("psu", 54, 60)]  # 10 s in total against 7 s typical
    assert len(merge_fragments(pieces, TYPICAL, tolerance=1.2)) == 2
    assert len(merge_fragments(pieces, TYPICAL, tolerance=1.5)) == 1


def test_typical_duration_is_stored_with_the_references(tmp_path):
    examples = [ReferenceExample("psu", "a psu", (b"\xff\xd8a",), ("v1",), typical_seconds=6.8), ReferenceExample("idle", "nothing", (b"\xff\xd8b",), ("v2",))]
    save_references(tmp_path / "refs", examples, note="t")
    loaded = load_references(tmp_path / "refs")
    assert [e.typical_seconds for e in loaded] == [6.8, None]


VOCAB = [EventDef(label="psu_installed", description="power supply seated")]


def test_backend_merges_over_segmented_actions_using_the_reference_durations(make_video):
    references = [ReferenceExample("psu_installed", "a psu", (b"img",), typical_seconds=8.0)]
    fake = FakeLLM(json_handler=lambda *_: {"hands_working": True, "part_handled": "psu_installed", "label": "psu_installed", "confidence": 0.9, "description": "psu"})

    def observe(**kwargs):
        backend = DDMVLMBackend(fake, "vlm", FakeRunner([4.0, 7.0]), votes=1, references=references, **kwargs)
        return backend.observe(make_video(10), "VID-M", VOCAB, "servers")[0]

    assert [(e.start, e.end) for e in observe().events] == [(0.0, 7.0), (7.0, 10.0)]  # 4 s + 3 s fused; the last piece is beyond 1.2 x 8 s
    assert len(observe(merge_tolerance=None).events) == 3  # switched off: every cut keeps its own event
    no_durations = DDMVLMBackend(fake, "vlm", FakeRunner([4.0, 7.0]), votes=1, references=[ReferenceExample("psu_installed", "a psu", (b"img",))])
    assert len(no_durations.observe(make_video(10), "VID-N", VOCAB, "servers")[0].events) == 3  # references from before durations existed
