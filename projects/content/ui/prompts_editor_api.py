"""HTTP API для чтения/записи markdown-промптов (Bearer PROMPTS_EDITOR_SECRET)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.config.settings import Settings
from services.llm.system_prompt_loader import (
    read_global_model_policy_raw,
    read_system_prompt_raw,
    SystemPromptError,
    write_global_model_policy_raw,
    write_system_prompt_raw,
)


class PromptFileBody(BaseModel):
    content: str = Field(..., description="Полное содержимое .md файла")


def _require_editor_secret(request: Request, settings: Settings) -> None:
    secret = (settings.prompts_editor_secret or "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="PROMPTS_EDITOR_SECRET не задан в окружении backend",
        )
    auth = (request.headers.get("Authorization") or "").strip()
    if auth != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Неверный или отсутствующий токен")


def create_prompts_editor_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/prompts", tags=["prompts-editor"])

    def guard(request: Request) -> None:
        _require_editor_secret(request, settings)

    @router.get("/system", dependencies=[Depends(guard)])
    async def get_system_prompt() -> dict[str, Any]:
        try:
            content = read_system_prompt_raw()
        except SystemPromptError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"path": "prompts/system_prompt.md", "content": content}

    @router.put("/system", dependencies=[Depends(guard)])
    async def put_system_prompt(body: PromptFileBody) -> dict[str, Any]:
        try:
            write_system_prompt_raw(body.content)
        except SystemPromptError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "path": "prompts/system_prompt.md"}

    @router.get("/global-policy", dependencies=[Depends(guard)])
    async def get_global_policy() -> dict[str, Any]:
        content = read_global_model_policy_raw()
        return {"path": "prompts/global_model_policy.md", "content": content}

    @router.put("/global-policy", dependencies=[Depends(guard)])
    async def put_global_policy(body: PromptFileBody) -> dict[str, Any]:
        write_global_model_policy_raw(body.content)
        return {"ok": True, "path": "prompts/global_model_policy.md"}

    return router
