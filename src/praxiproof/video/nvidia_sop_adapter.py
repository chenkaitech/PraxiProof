from pathlib import Path
from typing import Any

import httpx

from praxiproof.ir.evidence import Evidence, sha256_file
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import EventDef
from praxiproof.video.frames import probe
from praxiproof.video.normalizer import RawSegment, normalize

_LIST_KEYS = ("steps", "events", "segments", "results")
_LABEL_KEYS = ("label", "step", "name", "action")


class NvidiaSOPBackend:
    # Response mapping is unconfirmed until the blueprint runs on the Spark (needs Docker GPU runtime + NGC key).

    name = "nvidia_sop"

    def __init__(self, endpoint: str, timeout: float = 1800.0):
        self.endpoint = endpoint
        self.timeout = timeout

    def observe(
        self, path: Path, source_id: str, vocabulary: list[EventDef], procedure: str
    ) -> tuple[Observation, list[Evidence]]:
        meta = probe(path)
        with path.open("rb") as fh:
            response = httpx.post(
                self.endpoint,
                files={"file": (path.name, fh, "video/mp4")},
                data={"procedure": procedure, "steps": ",".join(e.label for e in vocabulary)},
                timeout=self.timeout,
            )
        response.raise_for_status()
        segments = [s for item in _items(response.json()) if (s := _segment(item))]
        return normalize(segments, source_id, sha256_file(path), meta, self.name, "sop-inference-bp")


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    for key in _LIST_KEYS:
        if isinstance(payload.get(key), list):
            return payload[key]
    raise ValueError(f"unrecognized SOP blueprint response keys: {sorted(payload)[:10]}")


def _segment(item: dict[str, Any]) -> RawSegment | None:
    label = next((item[k] for k in _LABEL_KEYS if item.get(k)), None)
    start = item.get("start", item.get("start_time"))
    end = item.get("end", item.get("end_time"))
    if label is None or start is None or end is None:
        return None
    return RawSegment(
        label=str(label).strip().lower().replace(" ", "_").replace("-", "_"),
        description=str(item.get("description", label)),
        start=float(start),
        end=float(end),
        confidence=float(item.get("confidence", item.get("score", 1.0))),
    )
