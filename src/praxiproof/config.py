import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

EDITABLE = ("llm_model", "vlm_model", "vlm_thinking", "video_backend", "sop_bp_url", "min_confidence")
VIDEO_BACKENDS = ("local_vlm", "nvidia_sop")


@dataclass(frozen=True)
class Settings:
    ollama_url: str
    llm_model: str
    vlm_model: str
    vlm_thinking: bool
    video_backend: str
    sop_bp_url: str | None
    data_dir: Path
    keep_alive: str
    min_confidence: float


def get_settings() -> Settings:
    return Settings(
        ollama_url=os.environ.get("PRAXIPROOF_OLLAMA_URL", "http://127.0.0.1:11434"),
        llm_model=os.environ.get("PRAXIPROOF_LLM_MODEL", "qwen3.6:35b-a3b-q8_0"),
        vlm_model=os.environ.get("PRAXIPROOF_VLM_MODEL", "gemma4:31b"),
        vlm_thinking=os.environ.get("PRAXIPROOF_VLM_THINKING", "false").lower() in ("1", "true", "yes"),
        video_backend=os.environ.get("PRAXIPROOF_VIDEO_BACKEND", "local_vlm"),
        sop_bp_url=os.environ.get("PRAXIPROOF_SOP_BP_URL") or None,
        data_dir=Path(os.environ.get("PRAXIPROOF_DATA_DIR", "data")).resolve(),
        keep_alive=os.environ.get("PRAXIPROOF_KEEP_ALIVE", "5m"),
        min_confidence=float(os.environ.get("PRAXIPROOF_MIN_CONFIDENCE", "0.5")),
    )


def overrides_path(settings: Settings) -> Path:
    return settings.data_dir / "settings.json"


def load_overrides(settings: Settings) -> Settings:
    path = overrides_path(settings)
    if not path.exists():
        return settings
    saved = json.loads(path.read_text(encoding="utf-8"))
    return replace(settings, **{k: v for k, v in saved.items() if k in EDITABLE})


def save_overrides(settings: Settings) -> None:
    path = overrides_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: asdict(settings)[k] for k in EDITABLE}, indent=2), encoding="utf-8")


def validate_changes(changes: dict[str, Any], models: list[dict[str, Any]] | None) -> dict[str, Any]:
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise ValueError(f"settings not editable: {sorted(unknown)}")
    clean = dict(changes)
    if "video_backend" in clean and clean["video_backend"] not in VIDEO_BACKENDS:
        raise ValueError(f"video_backend must be one of {VIDEO_BACKENDS}")
    if "vlm_thinking" in clean:
        if not isinstance(clean["vlm_thinking"], bool):
            raise ValueError("vlm_thinking must be true or false")
    if "min_confidence" in clean:
        value = float(clean["min_confidence"])
        if not 0.0 <= value <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        clean["min_confidence"] = value
    if "sop_bp_url" in clean:
        url = (clean["sop_bp_url"] or "").strip() or None
        if url and not url.startswith(("http://", "https://")):
            raise ValueError("sop_bp_url must be an http(s) URL")
        clean["sop_bp_url"] = url
    if models is not None:
        capabilities = {m["name"]: set(m.get("capabilities", [])) for m in models}
        for key, needed in (("llm_model", "completion"), ("vlm_model", "vision")):
            if key not in clean:
                continue
            if clean[key] not in capabilities:
                raise ValueError(f"{key}: model {clean[key]} is not installed in Ollama")
            if needed not in capabilities[clean[key]]:
                raise ValueError(f"{key}: model {clean[key]} does not support {needed}")
    return clean
