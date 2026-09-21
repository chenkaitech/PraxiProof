import json
import re
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from praxiproof.eval.metrics import boundary_errors, match_events, sequence_similarity
from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.ir.requirement import EventDef
from praxiproof.video.backend import VideoBackend
from praxiproof.video.frames import FFmpegError, frame_at, probe
from praxiproof.video.references import ReferenceExample, save_references

PROCEDURE = "Server fan, power supply and cover installation"
CHUNK_NAME = re.compile(r"^(\d+)_(.+)_(\d+)_(\d+)\.mp4$", re.IGNORECASE)
ACTION_LABELS = {**{i: "fan_installed" for i in range(1, 7)}, 7: "psu_installed", 8: "psu_installed", 9: "cover_installed"}

VOCABULARY = [
    EventDef(label="fan_installed", description="A fan is installed: its connector is plugged in and the fan is pressed into its slot"),
    EventDef(label="psu_installed", description="A power supply is placed in its compartment and pressed in until the latch clicks"),
    EventDef(label="cover_installed", description="The server cover is placed on top of the server and the black latch is pressed to lock it"),
]


# Reference groups: identical repeated actions share one set of example images. Non-SOP chunks (action 10) show idle
# moments, including a server that is already closed, so the model learns that a finished state is not the cover step.
REFERENCE_GROUPS = [
    ("fan", range(1, 7), "a fan: a small dark square unit pressed down into one of the square slots in the middle of the chassis"),
    ("power_supply", (7, 8), "a power supply: a long flat metal module slid lengthwise into the compartment at the left edge of the chassis"),
    ("cover", (9,), "the server cover: a large flat metal lid over the open chassis, locked with the black latch in its centre"),
    ("idle", (10,), "no step being carried out: hands away from the server or resting, whether it is open or already closed"),
]
EDITS = ("compliant", "missing_cover", "psu_before_fans")


def chunk_dir(root: Path, video: str) -> Path:
    for split in ("train", "test"):
        folder = root / split / video
        if folder.is_dir():
            return folder
    raise FileNotFoundError(f"no action chunks for {video} under {root}")


def raw_video(root: Path, video: str) -> Path:
    return next(p for p in (root / "raw").iterdir() if p.stem == video)


def action_chunks(root: Path, video: str) -> list[tuple[int, int, Path]]:
    """(timeline position, action id, path) for each chunk of a recording, in timeline order."""
    chunks = []
    for path in chunk_dir(root, video).glob("*.mp4"):
        match = CHUNK_NAME.match(path.name)
        if match and match.group(2) == video:
            chunks.append((int(match.group(4)), int(match.group(1)), path))
    return sorted(chunks)


def load_ground_truth(root: Path, video: str) -> Observation:
    events, cursor = [], 0.0
    for timeline, action, path in action_chunks(root, video):
        duration = probe(path).duration
        if action in ACTION_LABELS:
            events.append(
                ObservedEvent(
                    event_id=f"G-{timeline:02d}",
                    label=ACTION_LABELS[action],
                    description=f"action {action}",
                    start=round(cursor, 2),
                    end=round(cursor + duration, 2),
                    confidence=1.0,
                )
            )
        cursor += duration
    return Observation(source_id=video, duration=round(cursor, 2), backend="ground_truth", events=events)


def score(predicted: list[ObservedEvent], gold: list[ObservedEvent]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "gold_events": len(gold),
        "predicted_events": len(predicted),
        "predicted_counts": dict(Counter(e.label for e in predicted)),
        "gold_counts": dict(Counter(e.label for e in gold)),
        "sequence_similarity": sequence_similarity(
            [e.label for e in sorted(predicted, key=lambda e: e.start)], [e.label for e in sorted(gold, key=lambda e: e.start)]
        ),
    }
    for threshold in (0.3, 0.5):
        matches = match_events(predicted, gold, threshold)
        result[f"matched@{threshold}"] = len(matches)
        if threshold == 0.3:
            result |= boundary_errors(matches)
            result["mean_iou@0.3"] = round(sum(i for _, _, i in matches) / len(matches), 3) if matches else 0.0
    return result


def _prf(tp: int, predicted: int, gold: int) -> dict[str, float]:
    precision = tp / predicted if predicted else 0.0
    recall = tp / gold if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def evaluate(root: Path, videos: list[str], backend: VideoBackend, out: Path | None = None) -> dict[str, Any]:
    per_video: dict[str, Any] = {}
    for video in videos:
        gold = load_ground_truth(root, video)
        started = time.monotonic()
        observation, _ = backend.observe(raw_video(root, video), video, VOCABULARY, PROCEDURE)
        per_video[video] = score(observation.events, gold.events) | {
            "seconds": round(time.monotonic() - started, 1),
            "video_duration": gold.duration,
            "predicted": [e.model_dump(include={"label", "start", "end", "confidence"}) for e in observation.sorted_events()],
            "gold": [e.model_dump(include={"label", "start", "end"}) for e in gold.events],
        }
        if out:
            out.write_text(json.dumps({"videos": per_video}, indent=2), encoding="utf-8")

    totals = {k: sum(v[k] for v in per_video.values()) for k in ("gold_events", "predicted_events", "matched@0.3", "matched@0.5")}
    summary = {
        "videos": len(per_video),
        "backend": backend.name,
        "detection@0.3": _prf(totals["matched@0.3"], totals["predicted_events"], totals["gold_events"]),
        "detection@0.5": _prf(totals["matched@0.5"], totals["predicted_events"], totals["gold_events"]),
        "mean_sequence_similarity": round(sum(v["sequence_similarity"] for v in per_video.values()) / len(per_video), 3) if per_video else 0.0,
        "mean_seconds_per_video": round(sum(v["seconds"] for v in per_video.values()) / len(per_video), 1) if per_video else 0.0,
    }
    report = {"summary": summary, "videos": per_video}
    if out:
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_references(
    root: Path, videos: list[str], out: Path, per_group: int = 3, position: float = 0.6, held_out: set[str] | None = None
) -> list[ReferenceExample]:
    """Take example frames of each action from training recordings; never from the recordings used for testing.

    `held_out` names the recordings being evaluated. It defaults to the dataset's own test split; cross-validation
    passes each fold's held-out recordings instead, since a recording that is test data in one fold is training
    data in another."""
    if held_out is None:
        held_out = {p.name for p in (root / "test").iterdir() if p.is_dir()} if (root / "test").is_dir() else set()
    if leaked := sorted(set(videos) & held_out):
        raise ValueError(f"reference images must not come from test recordings: {leaked}")
    chunks = {video: action_chunks(root, video) for video in videos}
    examples = []
    for group, (label, actions, description) in enumerate(REFERENCE_GROUPS):
        images, sources = [], []
        for i, video in enumerate(videos):
            if len(images) == per_group:
                break
            candidates = [(t, a, p) for t, a, p in chunks[video] if a in actions]
            if not candidates:
                continue
            _, action, path = candidates[(i + group) % len(candidates)]
            at = probe(path).duration * position
            images.append(frame_at(path, at))
            sources.append(f"{video} action {action} at {at:.1f}s into the chunk")
        examples.append(ReferenceExample(label=label, description=description, images=tuple(images), sources=tuple(sources)))
    note = f"Frames from the NVIDIA sop-server-fan-installation-data training recordings {', '.join(videos)}."
    save_references(out, examples, note)
    return examples


def edited_order(chunks: list[tuple[int, int, Path]], edit: str) -> list[Path]:
    if edit == "compliant":
        return [p for _, _, p in chunks]
    if edit == "missing_cover":
        return [p for _, a, p in chunks if a != 9]
    if edit == "psu_before_fans":
        psus = [p for _, a, p in chunks if a in (7, 8)]
        rest = [(a, p) for _, a, p in chunks if a not in (7, 8)]
        first_fan = next(i for i, (a, _) in enumerate(rest) if a in range(1, 7))
        paths = [p for _, p in rest]
        return paths[:first_fan] + psus + paths[first_fan:]
    raise ValueError(f"unknown edit {edit}; choose from {EDITS}")


def make_edits(root: Path, video: str, out: Path) -> list[Path]:
    """Re-assemble a recording's action chunks into a compliant copy and copies with a missing or reordered step."""
    chunks = action_chunks(root, video)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for edit in EDITS:
        target = out / f"{video}_{edit}.mp4"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as listing:
            listing.writelines(f"file '{p.resolve()}'\n" for p in edited_order(chunks, edit))
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing.name,
             "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", str(target)],
            capture_output=True,
            text=True,
        )
        Path(listing.name).unlink()
        if result.returncode != 0:
            raise FFmpegError(f"could not build {target.name}: {result.stderr.strip()[:300]}")
        written.append(target)
    return written
