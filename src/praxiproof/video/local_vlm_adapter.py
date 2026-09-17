from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praxiproof.ir.evidence import Evidence, sha256_file
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import EventDef
from praxiproof.llm import LLM
from praxiproof.video.frames import frame_at, probe, sample_times
from praxiproof.video.normalizer import RawSegment, normalize

SYSTEM_PROMPT = (
    "You watch still frames taken from a video of a technician performing a procedure. "
    "Report only what is visibly happening. Never guess events that are not shown."
)


@dataclass
class _Candidate:
    label: str
    first: float
    last: float
    confidence: float


class LocalVLMBackend:
    name = "local_vlm"

    def __init__(
        self,
        llm: LLM,
        model: str,
        window: float = 8.0,
        stride: float = 4.0,
        frames_per_window: int = 4,
        refine_radius: float = 4.0,
        max_refine_frames: int = 16,
        merge_gap: float = 6.0,
        frame_width: int = 640,
        thinking: bool = False,
    ):
        self.llm = llm
        self.model = model
        self.thinking = thinking
        self.window = window
        self.stride = stride
        self.frames_per_window = frames_per_window
        self.refine_radius = refine_radius
        self.max_refine_frames = max_refine_frames
        self.merge_gap = merge_gap
        self.frame_width = frame_width

    def observe(
        self, path: Path, source_id: str, vocabulary: list[EventDef], procedure: str
    ) -> tuple[Observation, list[Evidence]]:
        meta = probe(path)
        candidates = self._coarse(path, meta.duration, vocabulary, procedure)
        by_label = {e.label: e for e in vocabulary}
        segments = [self._refine(path, meta.duration, c, by_label[c.label], procedure) for c in candidates]
        return normalize(segments, source_id, sha256_file(path), meta, self.name, self.model, approximate=True)

    def _windows(self, duration: float) -> list[tuple[float, float]]:
        windows, start = [], 0.0
        while True:
            end = min(start + self.window, duration)
            windows.append((start, end))
            if end >= duration:
                return windows
            start += self.stride

    def _frames(self, path: Path, times: list[float]) -> tuple[list[bytes], str]:
        images = [frame_at(path, t, self.frame_width) for t in times]
        listing = "\n".join(f"Frame {i} at {t:.1f}s" for i, t in enumerate(times, start=1))
        return images, listing

    def _coarse(self, path: Path, duration: float, vocabulary: list[EventDef], procedure: str) -> list[_Candidate]:
        labels = [e.label for e in vocabulary]
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"enum": labels},
                            "frame": {"type": "integer"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["label", "frame", "confidence"],
                    },
                }
            },
            "required": ["events"],
        }
        catalog = "\n".join(f"- {e.label}: {e.description}" for e in vocabulary)
        hits: list[tuple[str, float, float]] = []
        for start, end in self._windows(duration):
            times = sample_times(start, end, self.frames_per_window)
            images, listing = self._frames(path, times)
            result = self.llm.chat_json(
                self.model,
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Procedure: {procedure}\n{listing}\n\nWhich of these events are visibly happening in "
                            f"these frames? For each, give the frame number where it is clearest and a confidence "
                            f"between 0 and 1. Return an empty list if none.\n{catalog}"
                        ),
                    },
                ],
                schema,
                images=images,
                think=None if self.thinking else False,
            )
            for item in result.get("events", []):
                frame = int(item.get("frame", 0))
                if item.get("label") in labels and 1 <= frame <= len(times):
                    hits.append((item["label"], times[frame - 1], _clamp(item.get("confidence", 0.0))))
        return self._merge(hits)

    def _merge(self, hits: list[tuple[str, float, float]]) -> list[_Candidate]:
        merged: list[_Candidate] = []
        for label, time, confidence in sorted(hits, key=lambda h: (h[0], h[1])):
            last = merged[-1] if merged else None
            if last and last.label == label and time - last.last <= self.merge_gap:
                last.last = time
                last.confidence = max(last.confidence, confidence)
            else:
                merged.append(_Candidate(label, time, time, confidence))
        return sorted(merged, key=lambda c: c.first)

    def _refine(self, path: Path, duration: float, candidate: _Candidate, event: EventDef, procedure: str) -> RawSegment:
        lo = max(candidate.first - self.refine_radius, 0.0)
        hi = min(candidate.last + self.refine_radius, duration)
        count = max(2, min(self.max_refine_frames, int(hi - lo) + 1))
        times = sample_times(lo, hi, count)
        step = (hi - lo) / count
        images, listing = self._frames(path, times)
        schema = {
            "type": "object",
            "properties": {
                "visible": {"type": "boolean"},
                "start_frame": {"type": ["integer", "null"]},
                "end_frame": {"type": ["integer", "null"]},
                "confidence": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["visible", "start_frame", "end_frame", "confidence", "description"],
        }
        result = self.llm.chat_json(
            self.model,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Procedure: {procedure}\n{listing}\n\nEvent '{event.label}': {event.description}\n"
                        "Give the first and last frame numbers in which this event is happening, a confidence between "
                        "0 and 1, and a one-sentence description of what is shown. If it is not visible, set "
                        "visible=false and the frame numbers to null."
                    ),
                },
            ],
            schema,
            images=images,
            think=None if self.thinking else False,
        )
        first, last = result.get("start_frame"), result.get("end_frame")
        if result.get("visible") and isinstance(first, int) and isinstance(last, int) and 1 <= first <= last <= len(times):
            return RawSegment(
                label=candidate.label,
                description=result.get("description", ""),
                start=max(times[first - 1] - step / 2, 0.0),
                end=min(times[last - 1] + step / 2, duration),
                confidence=min(candidate.confidence, _clamp(result.get("confidence", candidate.confidence))),
                uncertainty=round(step / 2, 2),
            )
        return RawSegment(
            label=candidate.label,
            description=f"Seen in coarse pass only; not confirmed on closer inspection. {result.get('description', '')}".strip(),
            start=candidate.first,
            end=candidate.last,
            confidence=min(candidate.confidence, 0.4),
            uncertainty=round(self.window / self.frames_per_window, 2),
        )


def _clamp(value: Any) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0
