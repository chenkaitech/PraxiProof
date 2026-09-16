import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from praxiproof import __version__
from praxiproof.config import Settings, get_settings
from praxiproof.llm import LLM, LLMError, OllamaClient
from praxiproof.runtime.compliance_agent import ComplianceAgent
from praxiproof.service import PraxiProof
from praxiproof.store import NotFound
from praxiproof.video.backend import VideoBackend
from praxiproof.video.frames import FFmpegError

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_DEMO_DIR = Path(__file__).resolve().parents[3] / "demo"


class RunRequest(BaseModel):
    manual_id: str
    video_id: str | None = None
    observation: dict[str, Any] | None = None
    demo_observation: str | None = None


class ReviewRequest(BaseModel):
    decision: Literal["accepted", "rejected"] | None


class AskRequest(BaseModel):
    question: str
    run_id: str | None = None


def create_app(
    settings: Settings | None = None,
    llm: LLM | None = None,
    backend_factory: Callable[[], VideoBackend] | None = None,
    demo_dir: Path | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    llm = llm or OllamaClient(settings.ollama_url, settings.keep_alive)
    core = PraxiProof(settings, llm, backend_factory=backend_factory)
    agent = ComplianceAgent(core)
    demo_dir = demo_dir or Path(os.environ.get("PRAXIPROOF_DEMO_DIR", DEFAULT_DEMO_DIR))
    uploads = settings.data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="PraxiProof", version=__version__)
    app.state.core = core

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc.args[0])}, status_code=404)

    @app.exception_handler(ValueError)
    async def _bad_request(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(FFmpegError)
    async def _bad_media(_: Request, exc: FFmpegError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    def _save(upload: UploadFile) -> Path:
        fd, name = tempfile.mkstemp(dir=uploads, suffix=Path(upload.filename or "").suffix)
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(upload.file, out)
        return Path(name)

    @app.get("/health")
    def health() -> dict[str, Any]:
        wanted = {"llm": settings.llm_model, "vlm": settings.vlm_model}
        ping = getattr(llm, "ping", None)
        try:
            available = set(ping()) if ping else set(wanted.values())
            models = {k: any(m == v or m.split(":")[0] == v for m in available) for k, v in wanted.items()}
            ollama = "ok"
        except LLMError as exc:
            models, ollama = {k: False for k in wanted}, str(exc)
        return {"status": "ok", "version": __version__, "ollama": ollama, "models": models, "video_backend": settings.video_backend}

    @app.get("/api/settings")
    def app_settings() -> dict[str, Any]:
        return {
            "llm_model": settings.llm_model,
            "vlm_model": settings.vlm_model,
            "video_backend": settings.video_backend,
            "sop_blueprint_configured": bool(settings.sop_bp_url),
            "min_confidence": settings.min_confidence,
            "ollama_url": settings.ollama_url,
        }

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        return core.dashboard()

    @app.post("/api/manuals", status_code=202)
    def upload_manual(
        background: BackgroundTasks, file: UploadFile = File(...), procedure: str | None = Form(None)
    ) -> dict[str, Any]:
        record = core.add_manual(_save(file), file.filename or "manual", procedure or None)
        background.add_task(core.process_manual, record["id"])
        return record

    @app.get("/api/manuals")
    def list_manuals() -> list[dict[str, Any]]:
        return [{k: v for k, v in m.items() if k not in ("requirement_set", "rejected")} for m in core.store.list("manuals")]

    @app.get("/api/manuals/{manual_id}")
    def get_manual(manual_id: str) -> dict[str, Any]:
        record = core.store.get("manuals", manual_id)
        ids = [e for r in (record.get("requirement_set") or {}).get("requirements", []) for e in r["evidence_ids"]]
        evidence = core.store.evidence(ids)
        return record | {"evidence": {k: v.model_dump(mode="json") | {"citation": v.citation()} for k, v in evidence.items()}}

    @app.post("/api/manuals/{manual_id}/recompile", status_code=202)
    def recompile_manual(manual_id: str, background: BackgroundTasks) -> dict[str, Any]:
        record = core.store.update("manuals", manual_id, status="queued", error=None)
        background.add_task(core.process_manual, manual_id)
        return record

    @app.post("/api/videos", status_code=201)
    def upload_video(file: UploadFile = File(...)) -> dict[str, Any]:
        path = _save(file)
        try:
            return core.add_video(path, file.filename or "video.mp4")
        except FFmpegError:
            path.unlink(missing_ok=True)
            raise

    @app.get("/api/videos")
    def list_videos() -> list[dict[str, Any]]:
        return core.store.list("videos")

    @app.get("/api/videos/{video_id}/file")
    def video_file(video_id: str) -> FileResponse:
        return FileResponse(core.store.get("videos", video_id)["path"])

    @app.get("/api/videos/{video_id}/frame")
    def video_frame(video_id: str, t: float = 0.0) -> Response:
        return Response(core.frame(video_id, t), media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/demo/observations")
    def demo_observations() -> list[dict[str, Any]]:
        folder = demo_dir / "observations"
        return [
            {"name": p.stem, "title": json.loads(p.read_text(encoding="utf-8")).get("title", p.stem)}
            for p in sorted(folder.glob("*.json"))
        ]

    @app.post("/api/runs", status_code=202)
    def start_run(body: RunRequest, background: BackgroundTasks) -> dict[str, Any]:
        observation, label = body.observation, None
        if body.demo_observation:
            path = demo_dir / "observations" / f"{Path(body.demo_observation).name}.json"
            if not path.exists():
                raise NotFound(f"demo observation {body.demo_observation} not found")
            fixture = json.loads(path.read_text(encoding="utf-8"))
            observation, label = fixture["observation"], fixture.get("video_name", path.stem)
        record = core.create_run(body.manual_id, body.video_id, observation, label)
        background.add_task(core.process_run, record["id"])
        return record

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        return [
            {k: r.get(k) for k in ("id", "created_at", "manual_id", "manual_name", "video_id", "video_name", "procedure", "status", "stage", "error", "result", "violations", "counts")}
            for r in core.store.list("runs")
        ]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = core.store.get("runs", run_id)
        if run.get("status") == "done":
            run["findings"] = core.finding_details(run)
            report = run["report"]
            ids = [e for v in report["verdicts"] for e in v["requirement_evidence_ids"] + v["observation_evidence_ids"]]
            run["evidence"] = {k: v.model_dump(mode="json") | {"citation": v.citation()} for k, v in core.store.evidence(ids).items()}
        return run

    @app.post("/api/runs/{run_id}/verdicts/{rule_id}/review")
    def review(run_id: str, rule_id: str, body: ReviewRequest) -> dict[str, Any]:
        return core.review(run_id, rule_id, body.decision)

    @app.post("/api/runs/{run_id}/skill", status_code=201)
    def compile_skill(run_id: str) -> dict[str, Any]:
        return core.compile_skill(run_id)

    @app.get("/api/skills")
    def list_skills() -> list[dict[str, Any]]:
        return core.store.list("skills")

    @app.get("/api/skills/{skill_id}/skill.md")
    def skill_md(skill_id: str) -> PlainTextResponse:
        return PlainTextResponse(core.skill_markdown(skill_id), media_type="text/markdown")

    @app.get("/api/skills/{skill_id}/download")
    def skill_download(skill_id: str) -> Response:
        name, data = core.skill_zip(skill_id)
        return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})

    @app.get("/api/evidence/{evidence_id}")
    def evidence(evidence_id: str) -> dict[str, Any]:
        item = core.store.evidence([evidence_id]).get(evidence_id)
        if item is None:
            raise NotFound(f"evidence {evidence_id} not found")
        return item.model_dump(mode="json") | {"citation": item.citation()}

    @app.post("/api/agent/ask")
    def ask(body: AskRequest) -> dict[str, Any]:
        try:
            return agent.ask(body.question, body.run_id)
        except LLMError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
