import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class DocumentLocator(BaseModel):
    kind: Literal["document"] = "document"
    page: int | None = None
    section: str | None = None
    block_index: int
    bbox: list[float] | None = None


class VideoLocator(BaseModel):
    kind: Literal["video"] = "video"
    start: float
    end: float
    frame_start: int | None = None
    frame_end: int | None = None


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"EV-{uuid.uuid4().hex[:10]}")
    source_type: Literal["document", "video"]
    source_id: str
    sha256: str
    locator: Annotated[DocumentLocator | VideoLocator, Field(discriminator="kind")]
    text: str | None = None
    extractor: str
    extractor_version: str | None = None
    model: str | None = None
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def citation(self) -> str:
        loc = self.locator
        if isinstance(loc, DocumentLocator):
            if loc.page is not None:
                return f"p.{loc.page}"
            return loc.section or f"block {loc.block_index}"
        return f"{format_timestamp(loc.start)} to {format_timestamp(loc.end)}"


def format_timestamp(seconds: float) -> str:
    minutes, secs = divmod(max(seconds, 0.0), 60)
    return f"{int(minutes):02d}:{secs:04.1f}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
