"""Зависимости Dream Lite для Telegram-хендлеров."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.dreams.dream_orchestrator import DreamPipelineService
from storage.dream_lite_asset_repository import DreamLiteAssetRepository
from storage.dream_lite_run_repository import DreamLiteRunRepository
from storage.dream_lite_summary_repository import DreamLiteSummaryRepository


class DreamLiteResourcesMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        dream_lite_run_repo: DreamLiteRunRepository | None,
        dream_pipeline: DreamPipelineService | None,
        dream_lite_summary_repo: DreamLiteSummaryRepository | None = None,
        dream_lite_asset_repo: DreamLiteAssetRepository | None = None,
    ) -> None:
        super().__init__()
        self._repo = dream_lite_run_repo
        self._dream = dream_pipeline
        self._summary_repo = dream_lite_summary_repo
        self._asset_repo = dream_lite_asset_repo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["dream_lite_run_repo"] = self._repo
        data["dream_pipeline_service"] = self._dream
        data["dream_lite_summary_repo"] = self._summary_repo
        data["dream_lite_asset_repo"] = self._asset_repo
        return await handler(event, data)
