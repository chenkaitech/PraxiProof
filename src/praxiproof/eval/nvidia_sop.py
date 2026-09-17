import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from praxiproof.eval.metrics import boundary_errors, match_events, sequence_similarity
from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.ir.requirement import EventDef
from praxiproof.video.backend import VideoBackend
from praxiproof.video.frames import probe

PROCEDURE = "Server fan, power supply and cover installation"
CHUNK_NAME = re.compile(r"^(\d+)_(.+)_(\d+)_(\d+)\.mp4$", re.IGNORECASE)
ACTION_LABELS = {**{i: "fan_installed" for i in range(1, 7)}, 7: "psu_installed", 8: "psu_installed", 9: "cover_installed"}

VOCABULARY = [
    EventDef(label="fan_installed", description="A fan is installed: its connector is plugged in and the fan is pressed into its slot"),
    EventDef(label="psu_installed", description="A power supply is placed in its compartment and pressed in until the latch clicks"),
    EventDef(label="cover_installed", description="The server cover is placed on top of the server and the black latch is pressed to lock it"),
]


def chunk_dir(root: Path, video: str) -> Path:
    for split in ("train", "test"):
        folder = root / split / video
        if folder.is_dir():
            return folder
    raise FileNotFoundError(f"no action chunks for {video} under {root}")


def raw_video(root: Path, video: str) -> Path:
    return next(p for p in (root / "raw").iterdir() if p.stem == video)


def load_ground_truth(root: Path, video: str) -> Observation:
    chunks = []
    for path in chunk_dir(root, video).glob("*.mp4"):
        match = CHUNK_NAME.match(path.name)
        if match and match.group(2) == video:
            chunks.append((int(match.group(4)), int(match.group(1)), path))
    events, cursor = [], 0.0
    for timeline, action, path in sorted(chunks):
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
