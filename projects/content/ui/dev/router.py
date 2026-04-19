"""Локальная dev-консоль: FastAPI + Jinja2 + HTMX (только 127.0.0.1)."""
from __future__ import annotations

import json
import re
import time
import uuid
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config.settings import Settings
from core.observability.repository import ObservabilityRepository
from services.assets.asset_source_service import (
    AssetSourceError,
    dream_asset_to_data_uri,
    load_local_file_as_data_uri,
)
from services.observability.dev_messages import get_message_detail, get_recent_messages
from services.observability.workspaces import get_workspace_detail, list_workspace_summaries
from services.tools.image_tools import tool_generate_image
from services.tools.video_tools import tool_image_to_video
from storage.chat_repository import ChatStoreRepository
from storage.dream_asset_repository import DreamAssetRepository
from storage.dream_run_repository import DreamRunRepository
from storage.dream_scene_repository import DreamSceneRepository
from storage.generated_frame_repository import GeneratedFrameRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.scene_video_repository import SceneVideoRepository
from storage.story_video_repository import StoryVideoRepository
from storage.repository import MessageRepository
from storage.video_job_repository import VideoJobRepository

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.filters["tojson"] = lambda v, indent=2: json.dumps(
    v,
    ensure_ascii=False,
    indent=indent,
    default=str,
)
_STATIC = Path(__file__).parent / "static"

_UPLOAD_ID_RE = re.compile(r"^[a-f0-9]{32}\.[a-z0-9]+$", re.IGNORECASE)

# Единый интервал polling dev UI (Messages, Dream Pipeline) — секунды для htmx `every Ns`
_DEV_POLL_INTERVAL_SEC = 2.5


def _upload_dir(settings: Settings) -> Path:
    return (settings.data_dir / "dev_uploads" / "video_inputs").resolve()


def _is_localhost(request: Request) -> bool:
    c = request.client
    if not c:
        return False
    host = c.host or ""
    if host in ("127.0.0.1", "::1", "localhost") or host.startswith("127."):
        return True
    try:
        ip = ip_address(host)
    except ValueError:
        return False
    # Allow private proxy hops (Docker bridge / local reverse proxy).
    return ip.is_private


def create_dev_console_router(
    settings: Settings,
    message_repo: MessageRepository,
    obs_repo: ObservabilityRepository,
    chat_store: ChatStoreRepository,
    dream_asset_repo: DreamAssetRepository,
    video_job_repo: VideoJobRepository,
    *,
    dream_run_repo: DreamRunRepository | None = None,
    dream_scene_repo: DreamSceneRepository | None = None,
    generated_frame_repo: GeneratedFrameRepository | None = None,
    generated_image_repo: GeneratedImageRepository | None = None,
    scene_video_repo: SceneVideoRepository | None = None,
    story_video_repo: StoryVideoRepository | None = None,
) -> APIRouter:
    async def _guard(request: Request) -> None:
        if not settings.dev_debug_ui_enabled:
            raise HTTPException(status_code=404, detail="Dev console disabled")
        if not _is_localhost(request):
            raise HTTPException(
                status_code=403,
                detail="Dev console only from localhost",
            )

    router = APIRouter(
        prefix="/dev",
        tags=["dev-console"],
        dependencies=[Depends(_guard)],
    )

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Any:
        css = _STATIC / "dev.css"
        js = _STATIC / "dev_ui.js"
        assets_version = int(
            max(
                css.stat().st_mtime if css.exists() else 0,
                js.stat().st_mtime if js.exists() else 0,
            )
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "title": "Dream Viz — Dev",
                "poll_interval_sec": _DEV_POLL_INTERVAL_SEC,
                "assets_version": assets_version,
            },
        )

    @router.get("/partials/messages/rows", response_class=HTMLResponse)
    async def partial_message_rows(request: Request) -> Any:
        items = get_recent_messages(message_repo, obs_repo, limit=150)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/message_rows.html",
            {"messages": items},
        )

    @router.post("/api/messages/clear", response_class=HTMLResponse)
    async def api_clear_messages(
        request: Request,
        scope: str = Form(...),
    ) -> Any:
        s = (scope or "").strip().lower()
        if s == "messages":
            await message_repo.delete_all_messages()
        elif s == "all":
            await message_repo.delete_all_messages()
            await obs_repo.delete_all_events()
            await chat_store.delete_all()
        else:
            raise HTTPException(status_code=400, detail="scope must be messages or all")
        items = get_recent_messages(message_repo, obs_repo, limit=150)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/messages_cleared_oob.html",
            {"messages": items},
        )

    @router.get("/partials/workspaces/list", response_class=HTMLResponse)
    async def partial_workspace_list(
        request: Request,
        period: str = Query("all"),
        sort_by: str = Query("last_activity"),
        search: str = Query(""),
        custom_start: str | None = Query(None),
        custom_end: str | None = Query(None),
    ) -> Any:
        items = list_workspace_summaries(
            message_repo,
            chat_store,
            dream_asset_repo,
            video_job_repo,
            dream_run_repo,
            generated_frame_repo,
            generated_image_repo,
            scene_video_repo,
            story_video_repo,
            period=period,
            sort_by=sort_by,
            search=search,
            custom_start=custom_start,
            custom_end=custom_end,
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/workspaces_list.html",
            {
                "items": items,
                "period": period,
                "sort_by": sort_by,
                "search": search,
                "custom_start": custom_start or "",
                "custom_end": custom_end or "",
            },
        )

    @router.get("/partials/workspaces/{user_id}/detail", response_class=HTMLResponse)
    async def partial_workspace_detail(
        request: Request,
        user_id: int,
    ) -> Any:
        detail = get_workspace_detail(
            user_id,
            message_repo,
            chat_store,
            dream_asset_repo,
            video_job_repo,
            dream_run_repo,
            generated_frame_repo,
            generated_image_repo,
            scene_video_repo,
            story_video_repo,
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/workspace_detail.html",
            {"detail": detail},
        )

    @router.get(
        "/partials/messages/{message_id}/detail",
        response_class=HTMLResponse,
    )
    async def partial_message_detail(
        request: Request,
        message_id: str,
    ) -> Any:
        detail = get_message_detail(
            message_id, message_repo, obs_repo, chat_store=chat_store
        )
        if not detail:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/message_detail.html",
                {"error": "Сообщение не найдено", "detail": None},
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/message_detail.html",
            {"error": None, "detail": detail},
        )

    @router.post("/api/generate", response_class=HTMLResponse)
    async def api_generate(
        request: Request,
        prompt: str = Form(...),
        size: str = Form("1024*1536"),
        model: str = Form("qwen-image-2.0"),
        n: int = Form(1),
    ) -> Any:
        prompt_clean = (prompt or "").strip()
        if not prompt_clean:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/generate_result.html",
                {
                    "error": "Пустой prompt",
                    "ok": False,
                    "urls": [],
                    "prompt": "",
                    "seconds": 0.0,
                    "model": model,
                    "size": size,
                },
            )
        n = max(1, min(6, int(n)))
        t0 = time.perf_counter()
        result = tool_generate_image(
            prompt=prompt_clean,
            size=size,
            model=model,
            n=n,
        )
        elapsed = time.perf_counter() - t0
        if not result.ok:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/generate_result.html",
                {
                    "error": result.error or "Unknown error",
                    "ok": False,
                    "urls": [],
                    "prompt": prompt_clean,
                    "seconds": elapsed,
                    "model": model,
                    "size": size,
                },
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/generate_result.html",
            {
                "error": None,
                "ok": True,
                "urls": result.image_urls,
                "prompt": prompt_clean,
                "seconds": elapsed,
                "model": model,
                "size": size,
            },
        )

    @router.get("/partials/dream_assets/users", response_class=HTMLResponse)
    async def partial_dream_users(request: Request) -> Any:
        uids = dream_asset_repo.list_distinct_owner_ids_sync()
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_users.html",
            {"user_ids": uids},
        )

    @router.get("/partials/dream_assets/for_user", response_class=HTMLResponse)
    async def partial_dream_for_user(
        request: Request,
        uid: int = Query(..., description="telegram / owner user id"),
    ) -> Any:
        assets = dream_asset_repo.list_by_owner_sync(uid)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_assets_table.html",
            {"user_id": uid, "assets": assets},
        )

    @router.post("/api/video/upload", response_class=HTMLResponse)
    async def dev_video_upload(
        request: Request,
        file: UploadFile = File(...),
    ) -> Any:
        udir = _upload_dir(settings)
        udir.mkdir(parents=True, exist_ok=True)
        raw = await file.read()
        if len(raw) > 10 * 1024 * 1024:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/video_upload_result.html",
                {"error": "Файл больше 10 MB", "upload_id": None, "filename": None},
            )
        orig = file.filename or "image"
        ext = Path(orig).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
            ext = ".jpg"
        fname = f"{uuid.uuid4().hex}{ext}"
        path = udir / fname
        path.write_bytes(raw)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_upload_result.html",
            {"error": None, "upload_id": fname, "filename": orig},
        )

    @router.post("/api/video/jobs", response_class=HTMLResponse)
    async def dev_video_create_job(
        request: Request,
        source_mode: str = Form(...),
        prompt: str = Form(...),
        model: str = Form("wan2.7-i2v"),
        duration: int = Form(4),
        resolution: str = Form("720p"),
        dream_asset_id: str | None = Form(None),
        owner_user_id: str | None = Form(None),
        upload_id: str | None = Form(None),
    ) -> Any:
        prompt_clean = (prompt or "").strip()
        if not prompt_clean:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/video_error.html",
                {"message": "Пустой prompt"},
            )
        dur = max(2, min(10, int(duration)))
        try:
            if source_mode.strip() == "dream_asset":
                if not dream_asset_id:
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {
                            "message": "Выберите dream asset (радиокнопка) или переключите режим на загрузку файла.",
                        },
                    )
                asset = dream_asset_repo.find_by_id_sync(dream_asset_id)
                if not asset:
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {"message": "Asset не найден в MongoDB."},
                    )
                uri, meta = dream_asset_to_data_uri(
                    asset,
                    bot_token=settings.telegram_bot_token,
                )
                owner = str(asset.get("owner_user_id") or owner_user_id or "dev")
            elif source_mode.strip() == "upload":
                if not upload_id or not _UPLOAD_ID_RE.match(upload_id):
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {
                            "message": "Сначала загрузите файл (кнопка «Загрузить») или выберите dream asset.",
                        },
                    )
                path = _upload_dir(settings) / upload_id
                if not path.is_file():
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {"message": f"Файл загрузки не найден: {upload_id}"},
                    )
                uri, meta = load_local_file_as_data_uri(path)
                owner = (owner_user_id or "").strip() or "dev_upload"
            else:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/video_error.html",
                    {"message": f"Неизвестный source_mode: {source_mode}"},
                )
        except AssetSourceError as e:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/video_error.html",
                {"message": str(e)},
            )

        job_extra = {**meta, "dev_ui": True}
        result = tool_image_to_video(
            prompt=prompt_clean,
            image_url=uri,
            duration=dur,
            resolution=resolution,
            owner_user_id=owner,
            model=model,
            job_extra=job_extra,
        )
        job_id = result.get("job_id")
        if not job_id:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/video_error.html",
                {
                    "message": result.get("error") or "Не удалось создать job",
                },
            )
        job = video_job_repo.get_job_sync(job_id)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_job_tracker.html",
            {"job": job},
        )

    @router.get("/partials/video/users", response_class=HTMLResponse)
    async def partial_video_users(request: Request) -> Any:
        uids = dream_asset_repo.list_distinct_owner_ids_sync()
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_users.html",
            {"user_ids": uids},
        )

    @router.get("/partials/video/asset_picker", response_class=HTMLResponse)
    async def partial_video_asset_picker(
        request: Request,
        uid: int = Query(..., description="owner user id"),
    ) -> Any:
        assets = dream_asset_repo.list_by_owner_sync(uid, limit=120)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_asset_picker.html",
            {"uid": uid, "assets": assets, "error": None},
        )

    @router.get("/partials/video/job_tracker", response_class=HTMLResponse)
    async def partial_video_job_tracker(
        request: Request,
        job_id: str = Query(...),
    ) -> Any:
        job = video_job_repo.get_job_sync(job_id)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_job_tracker.html",
            {"job": job},
        )

    @router.get("/partials/video/jobs_rows", response_class=HTMLResponse)
    async def partial_video_jobs_rows(request: Request) -> Any:
        jobs = video_job_repo.list_recent_sync(limit=50)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_jobs_rows.html",
            {"jobs": jobs},
        )

    @router.get("/partials/video/job_detail", response_class=HTMLResponse)
    async def partial_video_job_detail(
        request: Request,
        job_id: str = Query(...),
    ) -> Any:
        job = video_job_repo.get_job_sync(job_id)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_job_detail.html",
            {"job": job},
        )

    if (
        dream_run_repo is not None
        and dream_scene_repo is not None
        and generated_frame_repo is not None
        and scene_video_repo is not None
    ):

        @router.get("/partials/dream/sidebar", response_class=HTMLResponse)
        async def partial_dream_sidebar(request: Request) -> Any:
            runs = await dream_run_repo.list_recent(limit=50)
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_sidebar.html",
                {"runs": runs, "poll_interval_sec": _DEV_POLL_INTERVAL_SEC},
            )

        @router.get("/partials/dream/pipeline", response_class=HTMLResponse)
        async def partial_dream_pipeline(
            request: Request,
            run_id: str = Query(...),
        ) -> Any:
            run = await dream_run_repo.find_by_id(run_id)
            if not run:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/dream_pipeline_detail.html",
                    {
                        "error": "Запуск не найден",
                        "run": None,
                        "cards": [],
                        "poll_interval_sec": _DEV_POLL_INTERVAL_SEC,
                    },
                )
            drid = run_id
            scenes = await dream_scene_repo.list_by_dream_run(drid)
            frames = await generated_frame_repo.list_by_dream_run(drid)
            svs = await scene_video_repo.list_by_dream_run(drid)
            by_idx: dict[int, dict[str, Any]] = {}
            for s in scenes:
                idx = int(s.get("scene_index") or 0)
                if idx:
                    by_idx.setdefault(idx, {})["scene"] = s
            for f in frames:
                idx = int(f.get("scene_index") or 0)
                if idx:
                    by_idx.setdefault(idx, {})["frame"] = f
            for v in svs:
                idx = int(v.get("scene_index") or 0)
                if idx:
                    by_idx.setdefault(idx, {})["scene_video"] = v
            order = sorted(by_idx.keys())
            cards = [{"scene_index": i, **by_idx[i]} for i in order]
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_detail.html",
                {
                    "error": None,
                    "run": run,
                    "cards": cards,
                    "poll_interval_sec": _DEV_POLL_INTERVAL_SEC,
                },
            )

    return router


def mount_dev_static(app: Any) -> None:
    if _STATIC.is_dir():
        app.mount(
            "/dev/static",
            StaticFiles(directory=str(_STATIC)),
            name="dev_console_static",
        )


def create_legacy_debug_redirect_router(settings: Settings) -> APIRouter:
    """Редирект /dev/debug/* → /dev/* (старая консоль снята)."""

    async def _guard(request: Request) -> None:
        if not settings.dev_debug_ui_enabled:
            raise HTTPException(status_code=404, detail="Dev console disabled")
        if not _is_localhost(request):
            raise HTTPException(status_code=403, detail="Dev console only from localhost")

    r = APIRouter(prefix="/dev/debug", dependencies=[Depends(_guard)])

    @r.get("", include_in_schema=False)
    @r.get("/", include_in_schema=False)
    async def redir_root() -> RedirectResponse:
        return RedirectResponse(url="/dev/", status_code=302)

    return r
