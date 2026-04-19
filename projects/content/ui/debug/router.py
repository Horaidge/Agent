"""Локальная read-only debug-консоль: FastAPI + Jinja2 + polling (только localhost)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymongo import MongoClient

from bot.webhook_management import get_webhook_info
from core.config.settings import Settings
from core.observability.repository import ObservabilityRepository
from storage.repository import MessageRepository

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_STATIC = Path(__file__).parent / "static"


def _is_localhost(request: Request) -> bool:
    c = request.client
    if not c:
        return False
    host = c.host or ""
    return host in ("127.0.0.1", "::1", "localhost") or host.startswith("127.")


def create_debug_router(
    settings: Settings,
    message_repo: MessageRepository,
    obs_repo: ObservabilityRepository,
    sync_client: MongoClient,
) -> APIRouter:
    async def _guard(_request: Request) -> None:
        if not settings.dev_debug_ui_enabled:
            raise HTTPException(status_code=404, detail="Debug UI disabled")
        if not _is_localhost(_request):
            raise HTTPException(
                status_code=403,
                detail="Debug console only from localhost",
            )

    router = APIRouter(
        prefix="/dev/debug",
        tags=["dev-debug"],
        dependencies=[Depends(_guard)],
    )

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Any:
        # Starlette: TemplateResponse(request, name, context) — не (name, dict)
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "title": "Dream Viz — Dev Console",
                "poll_interval_ms": 2500,
            },
        )

    @router.get("/api/events")
    def api_events(
        limit: int = Query(80, ge=1, le=500),
        trace_id: str | None = None,
        event_type: str | None = None,
        telegram_user_id: int | None = None,
        telegram_chat_id: int | None = None,
        since: str | None = None,
    ) -> dict[str, Any]:
        events = obs_repo.list_events_sync(
            limit=limit,
            trace_id=trace_id,
            event_type=event_type,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            since_iso=since,
        )
        for e in events:
            if "created_at" in e and hasattr(e["created_at"], "isoformat"):
                e["created_at"] = e["created_at"].isoformat()
        return {"events": events}

    @router.get("/api/traces")
    def api_traces(limit: int = Query(60, ge=1, le=200)) -> dict[str, Any]:
        return {"trace_ids": obs_repo.list_trace_ids_sync(limit=limit)}

    @router.get("/api/messages")
    def api_messages(
        limit: int = Query(80, ge=1, le=300),
        telegram_user_id: int | None = None,
        telegram_chat_id: int | None = None,
    ) -> dict[str, Any]:
        rows = message_repo.list_messages_debug_sync(
            limit=limit,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
        return {
            "messages": [
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat(),
                    "telegram_user_id": r.telegram_user_id,
                    "telegram_chat_id": r.telegram_chat_id,
                    "telegram_message_id": r.telegram_message_id,
                    "username": r.username,
                    "text": (r.text or "")[:2000],
                    "trace_id": r.trace_id,
                }
                for r in rows
            ]
        }

    @router.get("/api/mongo/message/{doc_id}")
    def api_mongo_message(doc_id: str) -> dict[str, Any]:
        doc = message_repo.get_message_by_id_sync(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        return {"document": doc}

    @router.get("/api/summary")
    def api_summary() -> dict[str, Any]:
        db = sync_client[settings.mongodb_db]
        cols = settings.mongodb_collection_messages, settings.mongodb_collection_observability
        counts = {}
        for name in cols:
            try:
                counts[name] = db[name].estimated_document_count()
            except Exception:  # noqa: BLE001
                counts[name] = None
        return {
            "mongodb_db": settings.mongodb_db,
            "collections": counts,
        }

    @router.get("/api/telegram/webhook-info")
    async def api_telegram_webhook_info(request: Request) -> dict[str, Any]:
        """Текущий webhook в Telegram (только если токен доступен процессу)."""
        from core.integrations.telegram_client import create_telegram_bot

        bot = create_telegram_bot(settings)
        try:
            info = await get_webhook_info(bot)
            led = info.last_error_date
            return {
                "url": info.url,
                "pending_update_count": info.pending_update_count,
                "last_error_message": info.last_error_message,
                "last_error_date": led.isoformat() if led is not None else None,
            }
        finally:
            await bot.session.close()

    return router


def mount_debug_static(app: Any) -> None:
    """Статика для /dev/debug/static/*"""
    if _STATIC.is_dir():
        app.mount(
            "/dev/debug/static",
            StaticFiles(directory=str(_STATIC)),
            name="debug_static",
        )
