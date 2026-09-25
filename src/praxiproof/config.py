import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

EDITABLE = ("llm_model", "vlm_model", "vlm_thinking", "video_backend", "sop_bp_url", "ddm_checkpoint", "reference_dir", "min_confidence", "second_look")
VIDEO_BACKENDS = ("local_vlm", "ddm_vlm", "nvidia_sop")
LLM_PROVIDERS = ("ollama", "openai")
VLM_PROVIDERS = ("same", "ollama")


@dataclass(frozen=True)
class Settings:
    ollama_url: str
    llm_provider: str
    openai_base_url: str | None
    openai_api_key: str | None
    llm_model: str
    vlm_model: str
    vlm_thinking: bool
    video_backend: str
    sop_bp_url: str | None
    ddm_checkpoint: str | None
    reference_dir: str | None
    ddm_image: str
    ddm_code_dir: str
    data_dir: Path
    keep_alive: str
    min_confidence: float
    second_look: bool
    max_upload_mb: int = 2048
    api_token: str | None = None
    max_concurrent_jobs: int = 2
    vlm_provider: str = "same"
    openai_timeout: float = 60.0  # longest silence tolerated while a response streams in
    openai_stream: bool = True


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return value


def get_settings() -> Settings:
    llm_provider = os.environ.get("PRAXIPROOF_LLM_PROVIDER", "ollama")
    if llm_provider not in LLM_PROVIDERS:
        raise ValueError(f"PRAXIPROOF_LLM_PROVIDER must be one of {LLM_PROVIDERS}, got {llm_provider!r}")
    vlm_provider = os.environ.get("PRAXIPROOF_VLM_PROVIDER", "same")
    if vlm_provider not in VLM_PROVIDERS:
        raise ValueError(f"PRAXIPROOF_VLM_PROVIDER must be one of {VLM_PROVIDERS}, got {vlm_provider!r}")
    return Settings(
        ollama_url=os.environ.get("PRAXIPROOF_OLLAMA_URL", "http://127.0.0.1:11434"),
        llm_provider=llm_provider,
        openai_base_url=os.environ.get("PRAXIPROOF_OPENAI_BASE_URL") or None,
        openai_api_key=os.environ.get("PRAXIPROOF_OPENAI_API_KEY") or None,
        llm_model=os.environ.get("PRAXIPROOF_LLM_MODEL", "qwen3.6:35b-a3b-q8_0"),
        vlm_model=os.environ.get("PRAXIPROOF_VLM_MODEL", "gemma4:31b"),
        vlm_thinking=os.environ.get("PRAXIPROOF_VLM_THINKING", "false").lower() in ("1", "true", "yes"),
        video_backend=os.environ.get("PRAXIPROOF_VIDEO_BACKEND", "local_vlm"),
        sop_bp_url=os.environ.get("PRAXIPROOF_SOP_BP_URL") or None,
        ddm_checkpoint=os.environ.get("PRAXIPROOF_DDM_CHECKPOINT") or None,
        reference_dir=os.environ.get("PRAXIPROOF_REFERENCE_DIR") or None,
        ddm_image=os.environ.get("PRAXIPROOF_DDM_IMAGE", "praxiproof-ddm:26.08"),
        ddm_code_dir=os.environ.get("PRAXIPROOF_DDM_CODE_DIR", str(Path.home() / "ddm-train/ddm/DDM-Net")),
        data_dir=Path(os.environ.get("PRAXIPROOF_DATA_DIR", "data")).resolve(),
        keep_alive=os.environ.get("PRAXIPROOF_KEEP_ALIVE", "5m"),
        min_confidence=float(os.environ.get("PRAXIPROOF_MIN_CONFIDENCE", "0.5")),
        second_look=os.environ.get("PRAXIPROOF_SECOND_LOOK", "false").lower() in ("1", "true", "yes"),
        max_upload_mb=_positive_int("PRAXIPROOF_MAX_UPLOAD_MB", 2048),
        api_token=os.environ.get("PRAXIPROOF_API_TOKEN") or None,
        max_concurrent_jobs=_positive_int("PRAXIPROOF_MAX_CONCURRENT_JOBS", 2),
        vlm_provider=vlm_provider,
        openai_timeout=float(_positive_int("PRAXIPROOF_OPENAI_TIMEOUT", 60)),
        openai_stream=os.environ.get("PRAXIPROOF_OPENAI_STREAM", "true").lower() in ("1", "true", "yes"),
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


def validate_changes(changes: dict[str, Any], models: list[dict[str, Any]] | None, llm_in_models: bool = True) -> dict[str, Any]:
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise ValueError(f"settings not editable: {sorted(unknown)}")
    clean = dict(changes)
    if "video_backend" in clean and clean["video_backend"] not in VIDEO_BACKENDS:
        raise ValueError(f"video_backend must be one of {VIDEO_BACKENDS}")
    for flag in ("vlm_thinking", "second_look"):
        if flag in clean and not isinstance(clean[flag], bool):
            raise ValueError(f"{flag} must be true or false")
    if "min_confidence" in clean:
        value = float(clean["min_confidence"])
        if not 0.0 <= value <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        clean["min_confidence"] = value
    if "ddm_checkpoint" in clean:
        path = (clean["ddm_checkpoint"] or "").strip() or None
        if path and not Path(path).is_file():
            raise ValueError(f"ddm_checkpoint: file not found: {path}")
        clean["ddm_checkpoint"] = path
    if "reference_dir" in clean:
        path = (clean["reference_dir"] or "").strip() or None
        if path and not (Path(path) / "references.json").is_file():
            raise ValueError(f"reference_dir: no references.json in {path}")
        clean["reference_dir"] = path
    if "sop_bp_url" in clean:
        url = (clean["sop_bp_url"] or "").strip() or None
        if url and not url.startswith(("http://", "https://")):
            raise ValueError("sop_bp_url must be an http(s) URL")
        clean["sop_bp_url"] = url
    if models is not None:
        capabilities = {m["name"]: set(m.get("capabilities", [])) for m in models}
        for key, needed in (("llm_model", "completion"), ("vlm_model", "vision")):
            if key not in clean or (key == "llm_model" and not llm_in_models):
                continue  # the text model lives on another provider whose catalogue we cannot list
            if clean[key] not in capabilities:
                raise ValueError(f"{key}: model {clean[key]} is not installed in Ollama")
            if needed not in capabilities[clean[key]]:
                raise ValueError(f"{key}: model {clean[key]} does not support {needed}")
    return clean
