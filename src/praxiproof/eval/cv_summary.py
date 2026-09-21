"""Summarize the cross-validation run (deploy/ddm/cv/run_cv.sh).

Event-detection counts are pooled over recordings (micro-averaged), and uncertainty comes from a bootstrap that
resamples whole recordings — the recording is the independent unit, not the event. The "untouched" subset excludes
Install_12/13, the two recordings earlier design decisions (prompts, voting, window merging) were tuned on.

Usage: python -m praxiproof.eval.cv_summary <cv result dir> <output json>
"""
import json
import random
import sys
from pathlib import Path
from typing import Any

TUNED_ON = ("Install_12", "Install_13")
IOU_KEY = "matched@0.3"
BOOTSTRAP_ROUNDS = 10_000


def _f1(tp: int, predicted: int, gold: int) -> dict[str, float]:
    precision = tp / predicted if predicted else 0.0
    recall = tp / gold if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def _pooled(rows: list[dict[str, Any]]) -> dict[str, float]:
    return _f1(sum(r["tp"] for r in rows), sum(r["predicted"] for r in rows), sum(r["gold"] for r in rows))


def _interval(values: list[float]) -> list[float]:
    values = sorted(values)
    return [round(values[int(0.025 * len(values))], 3), round(values[int(0.975 * len(values)) - 1], 3)]


def _bootstrap_f1(rows: list[dict[str, Any]], seed: int = 0) -> list[float]:
    rng = random.Random(seed)
    return _interval([_pooled(rng.choices(rows, k=len(rows)))["f1"] for _ in range(BOOTSTRAP_ROUNDS)])


def _bootstrap_paired(a: list[dict[str, Any]], b: list[dict[str, Any]], seed: int = 0) -> dict[str, Any]:
    """F1 difference a-b, resampling the same recordings for both systems."""
    rng = random.Random(seed)
    idx = range(len(a))
    diffs = []
    for _ in range(BOOTSTRAP_ROUNDS):
        pick = rng.choices(idx, k=len(a))
        diffs.append(_pooled([a[i] for i in pick])["f1"] - _pooled([b[i] for i in pick])["f1"])
    return {"difference": round(_pooled(a)["f1"] - _pooled(b)["f1"], 3), "ci95": _interval(diffs), "recordings": len(a)}


def _rows(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        name: {"video": name, "gold": v["gold_events"], "predicted": v["predicted_events"], "tp": v[IOU_KEY],
               "sequence_similarity": v["sequence_similarity"], "seconds": v["seconds"]}
        for name, v in result["videos"].items()
    }


def _block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "recordings": len(rows),
        "gold_events": sum(r["gold"] for r in rows),
        **_pooled(rows),
        "f1_ci95": _bootstrap_f1(rows),
        "mean_sequence_similarity": round(sum(r["sequence_similarity"] for r in rows) / len(rows), 3),
        "mean_seconds_per_video": round(sum(r["seconds"] for r in rows) / len(rows), 1),
    }


def summarize(cv_dir: Path) -> dict[str, Any]:
    folds = {}
    for path in sorted(cv_dir.glob("fold*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "summary" in data:
            folds[path.stem] = _rows(data)
    ckpt_notes = {p.stem.removeprefix("ckpt_"): p.read_text().strip() for p in cv_dir.glob("ckpt_fold*.txt")}
    ddm = {name: row for rows in folds.values() for name, row in rows.items()}
    out: dict[str, Any] = {
        "protocol": {
            "recordings": len(ddm),
            "folds": {f: sorted(rows) for f, rows in folds.items()},
            "checkpoints": ckpt_notes,
            "note": "Each fold retrains DDM-Net and rebuilds the reference images from that fold's own training recordings; "
                    "a held-out recording is never seen by any component. Confidence intervals bootstrap over recordings.",
        },
        "ddm_vlm_cv": {"per_fold": {f: _pooled(list(rows.values())) | {"recordings": sorted(rows)} for f, rows in folds.items()}},
    }
    subsets = {"all": lambda n: True, "untouched": lambda n: n not in TUNED_ON}
    for label, keep in subsets.items():
        rows = [r for n, r in sorted(ddm.items()) if keep(n)]
        if rows:
            out["ddm_vlm_cv"][label] = _block(rows)

    base: dict[str, dict[str, Any]] = {}
    baseline_path = cv_dir / "local_vlm_all12.json"
    if baseline_path.exists():
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        if "summary" in data:
            base = _rows(data)
    if base:
        out["local_vlm"], out["paired_f1_difference"] = {}, {}
        for label, keep in subsets.items():
            names = [n for n in sorted(ddm) if keep(n) and n in base]
            if names:
                out["local_vlm"][label] = _block([base[n] for n in names])
                out["paired_f1_difference"][label] = _bootstrap_paired([ddm[n] for n in names], [base[n] for n in names])
    out["per_video"] = [
        {
            "video": n,
            "ddm_vlm_cv_f1": _f1(r["tp"], r["predicted"], r["gold"])["f1"],
            "local_vlm_f1": _f1(base[n]["tp"], base[n]["predicted"], base[n]["gold"])["f1"] if n in base else None,
        }
        for n, r in sorted(ddm.items(), key=lambda kv: int(kv[0].split("_")[1]))
    ]
    return out


if __name__ == "__main__":
    result = summarize(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_video"}, indent=2))
