from pathlib import Path
from typing import Protocol

from praxiproof.config import Settings
from praxiproof.ir.evidence import Evidence
from praxiproof.ir.observation import Observation
from praxiproof.ir.requirement import EventDef
from praxiproof.llm import LLM


class VideoBackend(Protocol):
    name: str

    def observe(
        self, path: Path, source_id: str, vocabulary: list[EventDef], procedure: str
    ) -> tuple[Observation, list[Evidence]]: ...


def get_backend(settings: Settings, llm: LLM) -> VideoBackend:
    if settings.video_backend == "nvidia_sop":
        from praxiproof.video.nvidia_sop_adapter import NvidiaSOPBackend

        if not settings.sop_bp_url:
            raise ValueError("PRAXIPROOF_SOP_BP_URL must be set to use the nvidia_sop video backend")
        return NvidiaSOPBackend(settings.sop_bp_url)
    if settings.video_backend == "local_vlm":
        from praxiproof.video.local_vlm_adapter import LocalVLMBackend

        return LocalVLMBackend(llm, settings.vlm_model, thinking=settings.vlm_thinking)
    raise ValueError(f"unknown video backend: {settings.video_backend}")
