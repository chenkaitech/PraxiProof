import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from praxiproof.ir.evidence import Evidence, sha256_file
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import EventDef
from praxiproof.llm import LLM
from praxiproof.verifier.aligner import Matcher
from praxiproof.video.frames import FFmpegError, frame_at, probe
from praxiproof.video.normalizer import RawSegment, normalize
from praxiproof.video.references import ReferenceExample, assign_references

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
        votes: int = 3,
        disagreement_confidence: float = 0.25,
        references: list[ReferenceExample] | None = None,
        matcher: Matcher | None = None,
    ):
        self.llm = llm
        self.model = model
        self.runner = runner
        self.thinking = thinking
        self.frames_per_segment = frames_per_segment
        self.min_segment_seconds = min_segment_seconds
        self.boundary_uncertainty = boundary_uncertainty
        self.frame_width = frame_width
        self.votes = max(1, votes)
        self.disagreement_confidence = disagreement_confidence
        self.references = references or []
        self.matcher = matcher

    def observe(
        self, path: Path, source_id: str, vocabulary: list[EventDef], procedure: str
    ) -> tuple[Observation, list[Evidence]]:
        meta = probe(path)
        cuts = [0.0] + sorted(b for b in self.runner.boundaries(path) if 0.0 < b < meta.duration) + [meta.duration]
        references = assign_references(self.references, vocabulary, self.matcher) if self.references else []
        segments = []
        for start, end in zip(cuts, cuts[1:]):
            if end - start < self.min_segment_seconds:
                continue
            label, confidence, description = self._vote(path, start, end, vocabulary, procedure, references)
            if label != NONE_LABEL:
                segments.append(
                    RawSegment(label=label, description=description, start=start, end=end, confidence=confidence, uncertainty=self.boundary_uncertainty)
                )
        model = f"ddm-net + {self.model}" + (f" + {sum(len(r.images) for _, r in references)} reference images" if references else "")
        return normalize(segments, source_id, sha256_file(path), meta, self.name, model, approximate=True)

    def _vote(
        self, path: Path, start: float, end: float, vocabulary: list[EventDef], procedure: str, references: list[tuple[str | None, ReferenceExample]]
    ) -> tuple[str, float, str]:
        """Label the segment from differently sampled frames; answers that disagree make the label low-confidence."""
        # Frame offsets within each sampling step, nearest the centre first: 0.5, then 0.25, 0.75, ...
        phases = sorted(((k + 1) / (self.votes + 1) for k in range(self.votes)), key=lambda x: abs(x - 0.5))
        answers: list[tuple[str, float, str]] = []
        for phase in phases:
            answers.append(self._classify(path, start, end, vocabulary, procedure, references, phase))
            if len(answers) == 2 and answers[0][0] == answers[1][0]:
                break
        counts = Counter(label for label, _, _ in answers)
        best = max(counts.values())
        # On a tie a step beats "none", and the more confident answer wins.
        label = max(
            (lbl for lbl, n in counts.items() if n == best),
            key=lambda lbl: (lbl != NONE_LABEL, max(c for a, c, _ in answers if a == lbl)),
        )
        agreeing = [(c, d) for a, c, d in answers if a == label]
        confidence = sum(c for c, _ in agreeing) / len(agreeing)
        if len(counts) > 1:
            confidence = min(confidence, self.disagreement_confidence)
        return label, round(confidence, 3), agreeing[0][1]

    def _classify(
        self,
        path: Path,
        start: float,
        end: float,
        vocabulary: list[EventDef],
        procedure: str,
        references: list[tuple[str | None, ReferenceExample]],
        phase: float = 0.5,
    ) -> tuple[str, float, str]:
        count = self.frames_per_segment
        step = (end - start) / count
        times = [round(start + step * (i + phase), 3) for i in range(count)]
        frames = [frame_at(path, t, self.frame_width) for t in times]
        catalog = "\n".join(f"- {e.label}: {e.description}" for e in vocabulary)
        reference_images: list[bytes] = []
        guide = []
        for target, example in references:
            first = len(reference_images) + 1
            reference_images.extend(example.images)
            guide.append(f"- images {first}-{len(reference_images)}: {target or NONE_LABEL + ' (not a step)'}: {example.description}")
        if reference_images:
            intro = (
                f"The first {len(reference_images)} images are reference examples from other recordings:\n" + "\n".join(guide)
                + f"\nThe last {len(frames)} images are the segment to label, in time order.\n"
            )
        else:
            intro = f"The {len(frames)} images are frames in time order from one segment of a procedure video.\n"
        # The model first reports what the hands do; a step label without hands at work is not trusted.
        # Keep this prompt short: longer wording made the model describe the reference images instead of the segment.
        schema = {
            "type": "object",
            "properties": {
                "hands_working": {"type": "boolean"},
                "part_handled": {"type": "string"},
                "label": {"enum": [e.label for e in vocabulary] + [NONE_LABEL]},
                "confidence": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["hands_working", "part_handled", "label", "confidence", "description"],
        }
        result = self.llm.chat_json(
            self.model,
            [
                {
                    "role": "user",
                    "content": (
                        f"{intro}First say whether the technician's hands are visibly working on the equipment in the segment "
                        f"(hands_working) and which part they are handling. Then say which step they perform. Answer with a step "
                        f"only when the hands carry it out in the segment; answer '{NONE_LABEL}' otherwise. Add a confidence "
                        f"between 0 and 1 and a one-sentence description.\n{catalog}"
                    ),
                },
            ],
            schema,
            images=reference_images + frames,
            think=None if self.thinking else False,
        )
        label = result.get("label") if result.get("label") in schema["properties"]["label"]["enum"] else NONE_LABEL
        if result.get("hands_working") is False:
            label = NONE_LABEL
        try:
            confidence = min(max(float(result.get("confidence", 0.0)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.0
        description = str(result.get("description", ""))
        return label, confidence, description
