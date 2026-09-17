import json
import subprocess
from pathlib import Path

import pytest

from praxiproof.eval.metrics import sequence_similarity
from praxiproof.eval.nvidia_sop import VOCABULARY, build_references, edited_order, evaluate, load_ground_truth
from praxiproof.ir.observation import Observation, ObservedEvent


def _clip(path, seconds):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=160x120:rate=10", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


@pytest.fixture
def dataset(tmp_path, make_video):
    root = tmp_path / "server_fan"
    chunks = root / "test" / "Install_12"
    chunks.mkdir(parents=True)
    (root / "raw").mkdir()
    for name, seconds in [("10_Install_12_1_1.mp4", 2), ("01_Install_12_1_2.mp4", 3), ("02_Install_12_1_3.mp4", 4), ("09_Install_12_1_4.mp4", 3), ("10_Install_12_2_5.mp4", 1)]:
        _clip(chunks / name, seconds)
    _clip(root / "raw" / "Install_12.MP4", 13)
    return root


def test_ground_truth_timeline(dataset):
    gold = load_ground_truth(dataset, "Install_12")
    assert [(e.label, e.start, e.end) for e in gold.events] == [
        ("fan_installed", 2.0, 5.0),
        ("fan_installed", 5.0, 9.0),
        ("cover_installed", 9.0, 12.0),
    ]
    assert gold.duration == 13.0


class ScriptedBackend:
    name = "scripted"

    def observe(self, path, source_id, vocabulary, procedure):
        assert vocabulary == VOCABULARY and path.name == "Install_12.MP4"
        events = [
            ObservedEvent(event_id="O-1", label="fan_installed", start=2.5, end=5.5, confidence=0.9),
            ObservedEvent(event_id="O-2", label="cover_installed", start=9.0, end=11.0, confidence=0.8),
            ObservedEvent(event_id="O-3", label="psu_installed", start=11.5, end=12.5, confidence=0.6),
        ]
        return Observation(source_id=source_id, duration=13, backend=self.name, events=events), []


def test_evaluate_scores_against_ground_truth(dataset, tmp_path):
    out = tmp_path / "report.json"
    report = evaluate(dataset, ["Install_12"], ScriptedBackend(), out)
    video = report["videos"]["Install_12"]
    assert (video["gold_events"], video["predicted_events"], video["matched@0.3"]) == (3, 3, 2)
    assert video["mean_start_error_s"] == 0.25 and video["mean_end_error_s"] == 0.75
    assert video["sequence_similarity"] == round(2 / 3, 3)
    assert report["summary"]["detection@0.3"] == {"precision": 0.667, "recall": 0.667, "f1": 0.667}
    assert json.loads(out.read_text())["summary"]["videos"] == 1


def test_sequence_similarity():
    assert sequence_similarity(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert sequence_similarity(["a", "c"], ["a", "b", "c"]) == 0.667
    assert sequence_similarity([], []) == 1.0


def test_edits_drop_the_cover_or_move_power_supplies_before_fans():
    # (timeline, action): non-SOP start, six fans, two power supplies, cover, non-SOP end
    actions = [10, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    chunks = [(i + 1, a, Path(f"{i + 1}_{a}")) for i, a in enumerate(actions)]
    names = lambda edit: [p.name.split("_")[1] for p in edited_order(chunks, edit)]
    assert names("compliant") == [str(a) for a in actions]
    assert names("missing_cover") == ["10", "1", "2", "3", "4", "5", "6", "7", "8", "10"]
    assert names("psu_before_fans") == ["10", "7", "8", "1", "2", "3", "4", "5", "6", "9", "10"]


def test_reference_images_refuse_test_recordings(tmp_path):
    (tmp_path / "test" / "Install_12").mkdir(parents=True)
    with pytest.raises(ValueError, match="Install_12"):
        build_references(tmp_path, ["Install_1", "Install_12"], tmp_path / "refs")
