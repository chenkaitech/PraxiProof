import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    ollama_url: str
    llm_model: str
    vlm_model: str
    video_backend: str
    sop_bp_url: str | None
    data_dir: Path
    keep_alive: str
    min_confidence: float


def get_settings() -> Settings:
    return Settings(
        ollama_url=os.environ.get("PRAXIPROOF_OLLAMA_URL", "http://127.0.0.1:11434"),
        llm_model=os.environ.get("PRAXIPROOF_LLM_MODEL", "qwen3.6:35b-a3b-q8_0"),
        vlm_model=os.environ.get("PRAXIPROOF_VLM_MODEL", "qwen3-vl:32b"),
        video_backend=os.environ.get("PRAXIPROOF_VIDEO_BACKEND", "local_vlm"),
        sop_bp_url=os.environ.get("PRAXIPROOF_SOP_BP_URL") or None,
        data_dir=Path(os.environ.get("PRAXIPROOF_DATA_DIR", "data")).resolve(),
        keep_alive=os.environ.get("PRAXIPROOF_KEEP_ALIVE", "5m"),
        min_confidence=float(os.environ.get("PRAXIPROOF_MIN_CONFIDENCE", "0.5")),
    )
