"""HTTP JSON: шаг 4 (план монтажа) и рендер i2v+склейка — для оркестраторов / Telegram backend."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from services.dreams.dream_orchestrator import DreamPipelineService
from services.observability.dream_pipeline_lite import (
    lite_compute_transition_plan,
    lite_dense_animate_fallback_plan,
    run_lite_i2v_concat_to_mp4,
)


def build_dream_lite_montage_json_router(
    dream_pipeline_service: DreamPipelineService | None,
) -> APIRouter:
    router = APIRouter(prefix="/api/dream/lite/montage", tags=["dream-lite-montage"])

    @router.post("/plan_json")
    async def api_montage_plan_json(body: dict[str, Any] = Body(...)) -> Any:
        if dream_pipeline_service is None:
            raise HTTPException(status_code=503, detail="dream_pipeline_service not configured")
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            raise HTTPException(status_code=503, detail="openai not configured")
        dream_text = str(body.get("dream_text") or "").strip()
        env_cards = body.get("env_cards") or []
        char_cards = body.get("char_cards") or []
        generated_frames = body.get("generated_frames") or body.get("frame_results") or []
        if not isinstance(env_cards, list):
            env_cards = []
        if not isinstance(char_cards, list):
            char_cards = []
        if not isinstance(generated_frames, list):
            raise HTTPException(status_code=400, detail="generated_frames must be a list")
        transition_plan_error = None
        try:
            transition_plan = await lite_compute_transition_plan(
                openai,
                dream_text=dream_text,
                env_cards=env_cards,
                char_cards=char_cards,
                generated_frames=generated_frames,
            )
        except ValueError as exc:
            transition_plan = lite_dense_animate_fallback_plan(len(generated_frames))
            transition_plan_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            transition_plan = lite_dense_animate_fallback_plan(len(generated_frames))
            transition_plan_error = str(exc)
        return JSONResponse(
            {
                "ok": True,
                "transition_plan": transition_plan,
                "transition_plan_error": transition_plan_error,
            },
        )

    @router.post("/render_json")
    async def api_montage_render_json(body: dict[str, Any] = Body(...)) -> Any:
        plan = body.get("transition_plan")
        frames = body.get("frame_results") or body.get("generated_frames") or []
        owner_user_id = str(body.get("owner_user_id") or "montage_json_anon").strip() or "montage_json_anon"
        if not isinstance(plan, dict):
            raise HTTPException(status_code=400, detail="transition_plan must be an object")
        if not isinstance(frames, list):
            raise HTTPException(status_code=400, detail="frame_results must be a list")
        out_base = str(body.get("output_basename") or "").strip()
        if not out_base:
            out_base = f"montage_{uuid.uuid4().hex[:16]}.mp4"
        tag = uuid.uuid4().hex[:12]
        try:
            final_vid = await asyncio.to_thread(
                run_lite_i2v_concat_to_mp4,
                transition_plan=plan,
                frame_results=frames,
                owner_user_id=owner_user_id,
                output_basename=out_base,
                lite_run_tag=tag,
            )
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {
                    "ok": False,
                    "final_video_url": None,
                    "error": str(exc),
                    "clips": [],
                },
                status_code=500,
            )
        return JSONResponse(
            {
                "ok": bool(final_vid.get("final_video_url")),
                "final_video_url": final_vid.get("final_video_url"),
                "error": final_vid.get("error"),
                "clips": final_vid.get("clips"),
            },
        )

    return router
