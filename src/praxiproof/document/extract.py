import json
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup
from pydantic import BaseModel

from praxiproof.ir.evidence import DocumentLocator, Evidence, sha256_file


class Block(BaseModel):
    index: int
    text: str
    page: int | None = None
    section: str | None = None
    bbox: list[float] | None = None


class ExtractedDocument(BaseModel):
    source_id: str
    filename: str
    sha256: str
    extractor: str
    extractor_version: str | None = None
    page_count: int | None = None
    blocks: list[Block]

    def evidence_for(self, block_index: int) -> Evidence:
        block = self.blocks[block_index]
        return Evidence(
            evidence_id=f"EV-{self.source_id}-B{block_index}",
            source_type="document",
            source_id=self.source_id,
            sha256=self.sha256,
            locator=DocumentLocator(page=block.page, section=block.section, block_index=block.index, bbox=block.bbox),
            text=block.text,
            extractor=self.extractor,
            extractor_version=self.extractor_version,
        )


class _Builder:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.section: str | None = None

    def heading(self, text: str) -> None:
        text = " ".join(text.split())
        if text:
            self.section = text
            self.add(text)

    def add(self, text: str, page: int | None = None, bbox: list[float] | None = None) -> None:
        text = " ".join(text.split()).lstrip("•►▶▸■◆◦ ")
        if text:
            self.blocks.append(Block(index=len(self.blocks), text=text, page=page, section=self.section, bbox=bbox))


def extract(path: Path, source_id: str, use_mineru: bool = True) -> ExtractedDocument:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if use_mineru and shutil.which("mineru"):
            blocks, extractor, version = _mineru(path)
        else:
            blocks, extractor, version = _pymupdf(path)
    elif suffix in (".html", ".htm"):
        blocks, extractor, version = _html(path.read_text(encoding="utf-8", errors="ignore")), "html", None
    elif suffix in (".md", ".markdown", ".txt"):
        blocks, extractor, version = _markdown(path.read_text(encoding="utf-8", errors="ignore")), "markdown", None
    else:
        raise ValueError(f"unsupported manual format: {suffix}")
    pages = {b.page for b in blocks if b.page is not None}
    return ExtractedDocument(
        source_id=source_id,
        filename=path.name,
        sha256=sha256_file(path),
        extractor=extractor,
        extractor_version=version,
        page_count=max(pages) if pages else None,
        blocks=blocks,
    )


def _pymupdf(path: Path) -> tuple[list[Block], str, str]:
    import fitz

    builder = _Builder()
    with fitz.open(path) as doc:
        sizes = [
            span["size"]
            for page in doc
            for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
            if span["text"].strip()
        ]
        body = statistics.median(sizes) if sizes else 10.0
        for page_number, page in enumerate(doc, start=1):
            for block in page.get_text("dict")["blocks"]:
                lines = block.get("lines", [])
                text = "\n".join("".join(span["text"] for span in line["spans"]) for line in lines)
                if not text.strip():
                    continue
                size = max(span["size"] for line in lines for span in line["spans"])
                if size >= body + 1.5 and len(text) < 120 and len(lines) <= 2:
                    builder.section = " ".join(text.split())
                builder.add(text, page=page_number, bbox=[round(v, 1) for v in block["bbox"]])
    return builder.blocks, "pymupdf", fitz.VersionBind


def _mineru(path: Path) -> tuple[list[Block], str, str | None]:
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(["mineru", "-p", str(path), "-o", out, "-b", "pipeline"], check=True, capture_output=True)
        content_list = next(Path(out).rglob("*_content_list.json"))
        items = json.loads(content_list.read_text(encoding="utf-8"))
    version = subprocess.run(["mineru", "--version"], capture_output=True, text=True).stdout.strip() or None
    return blocks_from_mineru(items), "mineru", version


def blocks_from_mineru(items: list[dict]) -> list[Block]:
    builder = _Builder()
    for item in items:
        text = item.get("text") or " ".join(item.get("list_items", []) or [])
        if item.get("type") == "table":
            text = item.get("table_body") or " ".join(item.get("table_caption", []))
        if not text or not text.strip():
            continue
        page = item["page_idx"] + 1 if "page_idx" in item else None
        if item.get("text_level"):
            builder.section = " ".join(text.split())
        builder.add(text, page=page, bbox=item.get("bbox"))
    return builder.blocks


def _html(markup: str) -> list[Block]:
    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    builder = _Builder()
    for element in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre"]):
        if element.find_parent(["li", "pre"]):
            continue
        text = element.get_text(" ", strip=True).rstrip("#").strip()
        if element.name.startswith("h"):
            builder.heading(text)
        else:
            builder.add(text)
    return builder.blocks


def _markdown(text: str) -> list[Block]:
    builder = _Builder()
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            builder.add(" ".join(paragraph))
            paragraph.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            builder.heading(stripped.lstrip("#"))
        elif not stripped:
            flush()
        elif stripped[:2] in ("- ", "* ") or stripped.split(". ", 1)[0].isdigit():
            flush()
            builder.add(stripped)
        else:
            paragraph.append(stripped)
    flush()
    return builder.blocks
