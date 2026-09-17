"""Run a trained DDM-Net boundary model over videos; executed inside the NVIDIA PyTorch container."""

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict

import av
import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader


def boundary_frames(scores: np.ndarray, scope: int, threshold: float) -> list[int]:
    # Same peak picking as the SOP training blueprint's validation (local maximum above threshold).
    peaks = []
    for i in range(2, len(scores) - 2):
        if scores[i] < threshold:
            continue
        window = scores[max(0, i - scope) : min(i + scope + 1, len(scores))]
        if scores[i] >= window.max() and np.count_nonzero(window == scores[i]) == 1:
            peaks.append(i)
    return peaks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True, help="DDM-Net source directory")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--videos", nargs="+", required=True, help="video files at the training resolution and fps")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    sys.path.insert(0, args.code)
    from datasets.ddm_val_dataset import DDMValStreamingDataset
    from datasets.default_aug import compose_default_augmentations
    from train_sop_lightning import SOPLightningModule

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    hparams = checkpoint["hyper_parameters"]
    frames_per_side = hparams.get("frames_per_side", 5)
    resolution = hparams.get("resolution", 224)
    module = SOPLightningModule(**{**hparams, "pretrained": False})
    module.load_state_dict(checkpoint["state_dict"])
    model = module.model.cuda().eval()

    with tempfile.TemporaryDirectory() as root:
        annotations, info = {}, {}
        for path in args.videos:
            video_id = os.path.splitext(os.path.basename(path))[0]
            os.symlink(os.path.abspath(path), os.path.join(root, f"{video_id}.mp4"))
            with av.open(path) as container:
                stream = container.streams.video[0]
                duration = float(stream.duration * stream.time_base) if stream.duration else float(container.duration / 1e6)
                info[video_id] = {"fps": float(stream.average_rate), "duration": duration}
            annotations[video_id] = [{"description": "whole video", "start_timestamp": 0.0, "end_timestamp": duration}]
        anno_path = os.path.join(root, "annotations.json")
        with open(anno_path, "w") as fh:
            json.dump(annotations, fh)

        dataset = DDMValStreamingDataset(
            annotation_file=anno_path,
            video_root=root,
            frames_per_side=frames_per_side,
            downsample=1,
            temporal_stride=1,
            chunk_duration=None,
            resolution=resolution,
            enable_load_balancing=False,
            transform=compose_default_augmentations({}, resolution),
        )
        loader = DataLoader(dataset, batch_size=args.batch_size, num_workers=args.workers, collate_fn=dataset.collate_fn)
        frame_scores: dict[str, dict[int, float]] = defaultdict(dict)
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
            for batch in loader:
                inp = batch["inp"].cuda(non_blocking=True)
                if inp.ndim == 6:
                    inp = inp.view((-1,) + inp.size()[2:])
                outputs, _, _ = model(inp)
                output = outputs[-1] if isinstance(outputs, (list, tuple)) else outputs
                probs = F.softmax(output.float(), dim=1)[:, 1].cpu().numpy()
                for video_id, frame, score in zip(batch["path"], batch["current_ids"].tolist(), probs):
                    frame_scores[video_id][int(frame)] = float(score)

    result = {}
    for video_id, meta in info.items():
        frames = sorted(frame_scores[video_id])
        scores = np.array([frame_scores[video_id][f] for f in frames])
        scope = max(3, int(meta["duration"] * meta["fps"] * 0.025 / 2))
        peaks = boundary_frames(scores, scope, args.threshold)
        result[video_id] = meta | {
            "boundaries": [round(frames[i] / meta["fps"], 3) for i in peaks],
            "scored_frames": len(frames),
        }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
