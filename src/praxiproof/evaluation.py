"""Measured results behind the "Evaluation" page: the video-backend ablation, VLM selection, the direct-VLM
baseline comparison, the cross-validation summary and the StepFun benchmark. The numbers live in docs/eval/*.json (raw outputs copied from
the DGX Spark runs); this module only reshapes them, it never computes or invents a score."""

import json
from pathlib import Path
from typing import Any

DEFAULT_EVAL_DIR = Path(__file__).resolve().parents[2] / "docs" / "eval"

# (result file, backend id) in the order they were tried; the last row is the shipped configuration.
_BACKEND_RUNS = [
    ("gemma4_test", "local_vlm"),
    ("gemma4_state_test", "local_vlm_state"),
    ("gemma4_nomerge_test", "local_vlm_nomerge"),
    ("ddm_vlm_test", "ddm_vlm"),
    ("ddm_vlm_refs_vote_oldckpt", "ddm_vlm_tuned_v1"),
    ("ddm_vlm_clean_refs_vote", "ddm_vlm_tuned"),
]
_SHIPPED = "ddm_vlm_tuned"


def _load(eval_dir: Path, name: str) -> Any | None:
    path = eval_dir / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _backends(eval_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for name, backend_id in _BACKEND_RUNS:
        data = _load(eval_dir, name)
        if not data:
            continue
        s = data["summary"]
        rows.append(
            {
                "id": backend_id,
                "precision": s["detection@0.3"]["precision"],
                "recall": s["detection@0.3"]["recall"],
                "f1": s["detection@0.3"]["f1"],
                "sequence_similarity": s["mean_sequence_similarity"],
                "seconds_per_video": s["mean_seconds_per_video"],
                "videos": s["videos"],
                "shipped": backend_id == _SHIPPED,
            }
        )
    return rows


def _vlm_selection(eval_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for name in ("vlm_select", "vlm_select2"):
        for key, r in (_load(eval_dir, name) or {}).items():
            if r["errors"]:
                continue  # a run that could not produce parseable output at all is not a comparable accuracy
            model = key.split(" ")[0]
            rows.append(
                {
                    "model": model,
                    "think_off": "think=False" in key,
                    "correct": r["correct"],
                    "cases": r["cases"],
                    "accuracy": r["accuracy"],
                    "seconds": r["mean_seconds"],
                }
            )
    # the schema-constrained duplicate of an identical result adds nothing
    seen, unique = set(), []
    for r in rows:
        k = (r["model"], r["think_off"], r["correct"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    return sorted(unique, key=lambda r: (-r["accuracy"], r["seconds"]))


def _baseline(eval_dir: Path) -> dict[str, Any] | None:
    data = _load(eval_dir, "baseline_vs_praxiproof")
    if not data:
        return None
    videos, violating, cleared = [], {"n": 0, "praxiproof_correct": 0, "samples": 0, "baseline_correct": 0, "baseline_false_compliant": 0}, {"n": 0, "praxiproof_cleared": 0, "baseline_correct": 0, "samples": 0}
    for name, v in data["videos"].items():
        labels = [b["label"] for b in v["baseline"]]
        # the pipeline reports a cleared recording as "PASS"; the truth column calls the same thing "Compliant"
        praxi = {"PASS": "Compliant"}.get(v["praxiproof"]["result"], v["praxiproof"]["result"])
        videos.append({"id": name, "truth": v["truth"], "baseline": labels, "praxiproof": praxi})
        if v["truth"] == "Compliant":
            cleared["n"] += 1
            cleared["praxiproof_cleared"] += praxi == "Compliant"
            cleared["samples"] += len(labels)
            cleared["baseline_correct"] += sum(l == "Compliant" for l in labels)
        else:
            violating["n"] += 1
            violating["praxiproof_correct"] += praxi == v["truth"]
            violating["samples"] += len(labels)
            violating["baseline_correct"] += sum(l == v["truth"] for l in labels)
            violating["baseline_false_compliant"] += sum(l == "Compliant" for l in labels)
    return {"videos": videos, "violating": violating, "compliant": cleared}


def _agents() -> list[dict[str, Any]]:
    from praxiproof.runtime import compliance_agent, rca_agent

    def names(tools: list[dict[str, Any]]) -> list[str]:
        return [t["function"]["name"] for t in tools]

    return [
        {"id": "compliance", "tools": names(compliance_agent.TOOLS)},
        {"id": "rca", "tools": names(rca_agent.TOOLS)},
    ]


def load_evaluation(eval_dir: Path | None = None) -> dict[str, Any]:
    eval_dir = eval_dir or DEFAULT_EVAL_DIR
    return {
        "backends": _backends(eval_dir),
        "vlm_selection": _vlm_selection(eval_dir),
        "baseline": _baseline(eval_dir),
        "cross_validation": _load(eval_dir, "cv_summary"),
        "second_look": _load(eval_dir, "second_look"),
        "stepfun": _load(eval_dir, "stepfun_compile_benchmark"),
        "agents": _agents(),
    }
