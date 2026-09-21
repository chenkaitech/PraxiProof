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
    if settings.video_backend == "ddm_vlm":
        from praxiproof.video.ddm_vlm_adapter import DDMRunner, DDMVLMBackend

        if not settings.ddm_checkpoint:
            raise ValueError("a DDM-Net checkpoint must be configured to use the ddm_vlm video backend")
        from praxiproof.verifier.aligner import llm_matcher
        from praxiproof.video.references import load_references

        runner = DDMRunner(settings.ddm_image, settings.ddm_code_dir, settings.ddm_checkpoint, settings.data_dir / "ddm_work")
        references = load_references(Path(settings.reference_dir)) if settings.reference_dir else None
        return DDMVLMBackend(
            llm,
            settings.vlm_model,
            runner,
            thinking=settings.vlm_thinking,
            disagreement_confidence=settings.min_confidence / 2,
            references=references,
            matcher=llm_matcher(llm, settings.llm_model),
            second_look_below=settings.min_confidence if settings.second_look else None,
        )
    if settings.video_backend == "local_vlm":
        from praxiproof.video.local_vlm_adapter import LocalVLMBackend

        return LocalVLMBackend(llm, settings.vlm_model, thinking=settings.vlm_thinking)
    raise ValueError(f"unknown video backend: {settings.video_backend}")
