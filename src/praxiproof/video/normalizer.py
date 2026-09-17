from pydantic import BaseModel, Field

from praxiproof.ir.evidence import Evidence, VideoLocator
from praxiproof.ir.observation import Observation, ObservedEvent
from praxiproof.video.frames import VideoMeta


class RawSegment(BaseModel):
    label: str
    description: str = ""
    start: float
    end: float
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: float = 0.0


def normalize(
    segments: list[RawSegment],
    source_id: str,
    sha256: str,
    meta: VideoMeta,
    backend: str,
    model: str | None,
    approximate: bool = False,
) -> tuple[Observation, list[Evidence]]:
    events, evidence = [], []
    for i, seg in enumerate(sorted(segments, key=lambda s: (s.start, s.end)), start=1):
        start = min(max(seg.start, 0.0), meta.duration)
        end = min(max(seg.end, start), meta.duration)
        item = Evidence(
            evidence_id=f"EV-{source_id}-O{i:03d}",
            source_type="video",
            source_id=source_id,
            sha256=sha256,
            locator=VideoLocator(start=start, end=end, frame_start=round(start * meta.fps), frame_end=round(end * meta.fps)),
            text=seg.description or seg.label,
            extractor=backend,
            model=model,
            confidence=seg.confidence,
        )
        evidence.append(item)
        events.append(
            ObservedEvent(
                event_id=f"O-{i:03d}",
                label=seg.label,
                description=seg.description,
                start=start,
                end=end,
                time_uncertainty=seg.uncertainty,
                confidence=seg.confidence,
                evidence_id=item.evidence_id,
            )
        )
    observation = Observation(
        source_id=source_id, duration=meta.duration, complete=True, approximate=approximate, backend=backend, model=model, events=events
    )
    return observation, evidence
