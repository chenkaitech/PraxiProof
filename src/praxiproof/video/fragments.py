"""Merge the pieces the boundary detector cut one physical action into.

DDM-Net finds where the picture changes, and a hand adjusting a part often changes it more than once, so one
installation can arrive as two or three consecutive segments carrying the same label. Counting rules (COUNT(psu >= 2))
then see phantom extra steps. Two consecutive segments with the same label are the same action when together they are
no longer than the action normally takes; the typical duration comes from the training recordings, so two genuinely
separate installations (which together are about twice as long) are never fused.
"""

from praxiproof.video.normalizer import RawSegment

DEFAULT_TOLERANCE = 1.2
MAX_GAP_SECONDS = 1.0


def merge_fragments(
    segments: list[RawSegment], typical_seconds: dict[str, float], tolerance: float = DEFAULT_TOLERANCE, max_gap: float = MAX_GAP_SECONDS
) -> list[RawSegment]:
    merged: list[RawSegment] = []
    counts: list[int] = []
    for segment in sorted(segments, key=lambda s: s.start):
        typical = typical_seconds.get(segment.label)
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and typical
            and previous.label == segment.label
            and segment.start - previous.end <= max_gap
            and segment.end - previous.start <= tolerance * typical
        ):
            best = segment if segment.confidence > previous.confidence else previous
            merged[-1] = previous.model_copy(
                update={
                    "end": segment.end,
                    "confidence": best.confidence,
                    "description": best.description,
                    "uncertainty": max(previous.uncertainty, segment.uncertainty),
                }
            )
            counts[-1] += 1
        else:
            merged.append(segment)
            counts.append(1)
    return [
        s.model_copy(update={"description": f"{s.description} [merged {n} fragments]".strip()}) if n > 1 else s
        for s, n in zip(merged, counts)
    ]
