"""Measure fragment merging on the cross-validation predictions, without re-running any model.

Merging happens after the per-segment votes, so applying it to the saved held-out predictions gives exactly what a
re-run would give. Each recording's typical action durations come only from the *other* folds' recordings, the way a
deployment builds them from its training recordings. The tolerance was chosen after looking at these same 12
recordings (the sweep below shows how flat the result is around it), so the improvement is reported as an estimate
on data the choice was made on.

Usage: python -m praxiproof.eval.fragment_merge <cv result dir> <merged cv output dir> <summary json>
"""
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from praxiproof.eval.cv_summary import _bootstrap_paired, _rows, summarize
from praxiproof.eval.metrics import match_events, sequence_similarity
from praxiproof.ir.observation import ObservedEvent
from praxiproof.video.fragments import DEFAULT_TOLERANCE, merge_fragments
from praxiproof.video.normalizer import RawSegment

SWEEP = (1.0, 1.1, 1.2, 1.3, 1.5)


def _load_folds(cv_dir: Path) -> dict[str, dict[str, Any]]:
    loaded = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(cv_dir.glob("fold*.json"))}
    return {name: data for name, data in loaded.items() if "videos" in data}  # folds.json only lists the split


def _events(items: list[dict[str, Any]]) -> list[ObservedEvent]:
    return [
        ObservedEvent(event_id=f"E{i}", label=e["label"], start=e["start"], end=e["end"], confidence=e.get("confidence", 1.0))
        for i, e in enumerate(items)
    ]


def _typical(recordings: dict[str, dict[str, Any]]) -> dict[str, float]:
    durations: dict[str, list[float]] = {}
    for video in recordings.values():
        for e in video["gold"]:
            durations.setdefault(e["label"], []).append(e["end"] - e["start"])
    return {label: statistics.median(values) for label, values in durations.items()}


def merge_recordings(cv_dir: Path, tolerance: float) -> dict[str, dict[str, Any]]:
    """foldN -> fold result in the cross-validation format, with each recording's predictions merged."""
    folds = _load_folds(cv_dir)
    out = {}
    for name, fold in folds.items():
        others = {n: v for other, f in folds.items() if other != name for n, v in f["videos"].items()}
        typical = _typical(others)
        videos = {}
        for video, result in fold["videos"].items():
            segments = [
                RawSegment(label=e["label"], start=e["start"], end=e["end"], confidence=e["confidence"], description=e.get("description", ""))
                for e in result["predicted"]
            ]
            merged = [
                {"label": s.label, "start": s.start, "end": s.end, "confidence": s.confidence}
                for s in merge_fragments(segments, typical, tolerance)
            ]
            gold = _events(result["gold"])
            matches = match_events(_events(merged), gold, 0.3)
            videos[video] = result | {
                "predicted": merged,
                "predicted_events": len(merged),
                "matched@0.3": len(matches),
                "sequence_similarity": sequence_similarity([e["label"] for e in merged], [e["label"] for e in result["gold"]]),
            }
        out[name] = {"summary": fold.get("summary", {}), "videos": videos}
    return out


def evaluate(cv_dir: Path, out_dir: Path, tolerance: float = DEFAULT_TOLERANCE) -> dict[str, Any]:
    before = summarize(cv_dir)["ddm_vlm_cv"]
    sweep = {}
    for k in SWEEP:
        merged = merge_recordings(cv_dir, k)
        rows = [r for fold in merged.values() for r in _rows(fold).values()]
        tp, predicted = sum(r["tp"] for r in rows), sum(r["predicted"] for r in rows)
        gold = sum(r["gold"] for r in rows)
        precision, recall = tp / predicted, tp / gold
        sweep[str(k)] = {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(2 * precision * recall / (precision + recall), 3), "events": predicted}

    out_dir.mkdir(parents=True, exist_ok=True)
    merged = merge_recordings(cv_dir, tolerance)
    for name, fold in merged.items():
        (out_dir / f"{name}.json").write_text(json.dumps(fold, indent=2), encoding="utf-8")
    after = summarize(out_dir)["ddm_vlm_cv"]
    original = {n: r for f in _load_folds(cv_dir).values() for n, r in _rows(f).items()}
    improved = {n: r for fold in merged.values() for n, r in _rows(fold).items()}
    names = sorted(original)
    return {
        "tolerance": tolerance,
        "note": "Typical durations come from the other folds' recordings. The tolerance was picked after inspecting these same recordings.",
        "before": {k: before[k] for k in ("all", "untouched")},
        "after": {k: after[k] for k in ("all", "untouched")},
        "paired_f1_difference": _bootstrap_paired([improved[n] for n in names], [original[n] for n in names]),
        "tolerance_sweep": sweep,
    }


if __name__ == "__main__":
    result = evaluate(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("before", "after", "paired_f1_difference", "tolerance_sweep")}, indent=1)[:2600])
