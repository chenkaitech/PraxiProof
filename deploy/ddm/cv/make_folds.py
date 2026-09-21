"""Build the 4-fold cross-validation splits over all 12 NVIDIA sop-server-fan recordings.

Each recording is held out exactly once. Annotations are rebuilt from the action-chunk files with the same
rule that produced ddm-train/data/train_clean.json (consecutive segments, one per chunk); `--check` proves
that by comparing against that file for the recordings it contains.

Usage: make_folds.py --data <server_fan dir> --out <ddm-train/data/cv> [--check <train_clean.json>]
"""
import argparse
import json
import re
from pathlib import Path

from praxiproof.eval.nvidia_sop import action_chunks
from praxiproof.video.frames import probe

VIDEOS = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]  # the dataset has no Install_2
# Install_12/13 are the two recordings earlier design decisions were tuned on; spread them over two folds.
FOLDS = {
    1: [1, 6, 12],
    2: [3, 7, 13],
    3: [4, 8, 10],
    4: [5, 9, 11],
}
VAL_PER_FOLD = 2


def labels(root: Path) -> dict[int, str]:
    out = {}
    for line in (root / "test" / "labels.txt").read_text().splitlines():
        m = re.match(r"\((\d+)\)", line.strip())
        if m:
            out[int(m.group(1))] = line.strip()
    return out


def annotate(root: Path, video: str, text: dict[int, str]) -> list[dict]:
    events, cursor = [], 0.0
    for _, action, path in action_chunks(root, video):
        duration = probe(path).duration
        events.append(
            {
                "event": f"event #{len(events) + 1}",
                "description": text[action],
                "start_timestamp": round(cursor, 3),
                "end_timestamp": round(cursor + duration, 3),
            }
        )
        cursor += duration
    return events


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--check", type=Path)
    args = ap.parse_args()
    text = labels(args.data)
    anno = {f"Install_{n}": annotate(args.data, f"Install_{n}", text) for n in VIDEOS}

    if args.check:
        reference = json.loads(args.check.read_text())
        worst = 0.0
        for name, events in reference.items():
            mine = anno[name]
            assert [e["description"] for e in mine] == [e["description"] for e in events], f"{name}: segment labels differ"
            worst = max(worst, max(abs(a["end_timestamp"] - b["end_timestamp"]) for a, b in zip(mine, events)))
        print(f"check ok: {len(reference)} recordings reproduce train_clean.json, max boundary difference {worst:.3f}s")

    args.out.mkdir(parents=True, exist_ok=True)
    plan = {}
    for fold, held in FOLDS.items():
        train_all = [n for n in VIDEOS if n not in held]
        val = [train_all[i] for i in (3, 7)][:VAL_PER_FOLD]  # fixed, spread over the sorted list
        train = [n for n in train_all if n not in val]
        for split, names in (("train", train), ("val", val)):
            (args.out / f"fold{fold}_{split}.json").write_text(json.dumps({f"Install_{n}": anno[f"Install_{n}"] for n in names}, indent=1))
        plan[f"fold{fold}"] = {"held_out": [f"Install_{n}" for n in held], "val": [f"Install_{n}" for n in val], "train": [f"Install_{n}" for n in train]}
    (args.out / "folds.json").write_text(json.dumps(plan, indent=2))
    print(json.dumps(plan, indent=1))


if __name__ == "__main__":
    main()
