import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from praxiproof.ir.evidence import Evidence, sha256_file
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import EventDef
from praxiproof.llm import LLM
from praxiproof.video.frames import FFmpegError, frame_at, probe, sample_times
from praxiproof.video.normalizer import RawSegment, normalize

NONE_LABEL = "none"
INFER_SCRIPT = Path(__file__).parent / "ddm" / "infer_ddm.py"
DDM_RESOLUTION = "320:180"
DDM_FPS = 30


class DDMError(RuntimeError):
    pass


class DDMRunner:
    """Runs the DDM-Net boundary model (trained with the NVIDIA SOP training blueprint) in a GPU container."""

    def __init__(self, image: str, code_dir: str, checkpoint: str, work_dir: Path, timeout: float = 1800.0):
        self.image = image
        self.code_dir = Path(code_dir)
        self.checkpoint = Path(checkpoint)
        self.work_dir = work_dir
        self.timeout = timeout

    def command(self, clip_dir: Path, clip_name: str) -> list[str]:
        return [
            "docker", "run", "--rm", "--device", "nvidia.com/gpu=all", "--ipc=host",
            "-v", f"{self.code_dir}:/workspace/ddm:ro",
            "-v", f"{self.checkpoint.parent}:/workspace/ckpt:ro",
            "-v", f"{INFER_SCRIPT}:/workspace/infer_ddm.py:ro",
            "-v", f"{clip_dir}:/workspace/clips:ro",
            self.image,
            "python", "/workspace/infer_ddm.py", "--code", "/workspace/ddm",
            "--checkpoint", f"/workspace/ckpt/{self.checkpoint.name}", "--videos", f"/workspace/clips/{clip_name}",
        ]

    def boundaries(self, video: Path) -> list[float]:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.work_dir) as tmp:
            clip = Path(tmp) / "clip.mp4"
            scaled = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"scale={DDM_RESOLUTION},fps={DDM_FPS}", "-an", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", str(clip)],
                capture_output=True,
                text=True,
            )
            if scaled.returncode != 0:
                raise FFmpegError(f"could not prepare video for DDM-Net: {scaled.stderr.strip()[:300]}")
            run = subprocess.run(self.command(Path(tmp), clip.name), capture_output=True, text=True, timeout=self.timeout)
        if run.returncode != 0:
            raise DDMError(f"DDM-Net inference failed: {run.stderr.strip()[-500:]}")
        result = json.loads(run.stdout.strip().splitlines()[-1])
        return result["clip"]["boundaries"]


class DDMVLMBackend:
    name = "ddm_vlm"

    def __init__(
        self,
        llm: LLM,
        model: str,
        runner: Any,
        thinking: bool = False,
        frames_per_segment: int = 8,
        min_segment_seconds: float = 1.0,
        boundary_uncertainty: float = 0.5,
        frame_width: int = 640,
    ):
        self.llm = llm
        self.model = model
        self.runner = runner
        self.thinking = thinking
        self.frames_per_segment = frames_per_segment
        self.min_segment_seconds = min_segment_seconds
        self.boundary_uncertainty = boundary_uncertainty
        self.frame_width = frame_width

    def observe(
        self, path: Path, source_id: str, vocabulary: list[EventDef], procedure: str
    ) -> tuple[Observation, list[Evidence]]:
        meta = probe(path)
        cuts = [0.0] + sorted(b for b in self.runner.boundaries(path) if 0.0 < b < meta.duration) + [meta.duration]
        segments = []
        for start, end in zip(cuts, cuts[1:]):
            if end - start < self.min_segment_seconds:
                continue
            label, confidence, description = self._classify(path, start, end, vocabulary, procedure)
            if label != NONE_LABEL:
                segments.append(
                    RawSegment(label=label, description=description, start=start, end=end, confidence=confidence, uncertainty=self.boundary_uncertainty)
                )
        return normalize(segments, source_id, sha256_file(path), meta, self.name, f"ddm-net + {self.model}", approximate=True)

    def _classify(self, path: Path, start: float, end: float, vocabulary: list[EventDef], procedure: str) -> tuple[str, float, str]:
        times = sample_times(start, end, self.frames_per_segment)
        images = [frame_at(path, t, self.frame_width) for t in times]
        catalog = "\n".join(f"- {e.label}: {e.description}" for e in vocabulary)
        schema = {
            "type": "object",
            "properties": {
                "label": {"enum": [e.label for e in vocabulary] + [NONE_LABEL]},
                "confidence": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["label", "confidence", "description"],
        }
        result = self.llm.chat_json(
            self.model,
            [
                {"role": "system", "content": "You watch frames from one action segment of a procedure video. Report only what is visibly happening."},
                {
                    "role": "user",
                    "content": (
                        f"Procedure: {procedure}\nThese {len(times)} frames are in time order, from {start:.1f}s to {end:.1f}s, "
                        f"and cover a single action.\nWhich step is the technician performing? Answer '{NONE_LABEL}' if it is "
                        f"none of these. Give a confidence between 0 and 1 and a one-sentence description.\n{catalog}"
                    ),
                },
            ],
            schema,
            images=images,
            think=None if self.thinking else False,
        )
        label = result.get("label") if result.get("label") in schema["properties"]["label"]["enum"] else NONE_LABEL
        try:
            confidence = min(max(float(result.get("confidence", 0.0)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return label, confidence, str(result.get("description", ""))
