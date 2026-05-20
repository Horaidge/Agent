"""Только callback Dream Lite (подтверждение монтажа) — без перехвата текста."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from dream_integration import get_dream_context

logger = logging.getLogger(__name__)

router = Router(name="dream_callbacks")


@router.callback_query(F.data.startswith("dlmc:"))
async def on_montage_confirm(callback: CallbackQuery) -> None:
    ctx = get_dream_context()
    if ctx is None:
        await callback.answer("Dream Lite недоступен.", show_alert=True)
        return

    from services.dreams.dream_lite_telegram_runner import resume_dream_lite_after_montage_confirm

    uid = callback.from_user.id if callback.from_user else 0
    rid = (callback.data or "").split(":", 1)[1].strip()
    doc = await ctx.dream_lite_run_repo.get_run(user_id=uid, lite_run_id=rid)
    if not doc or str(doc.get("step_phase") or "") != "montage_confirm":
        await callback.answer("Запуск устарел или уже подтверждён.", show_alert=True)
        return
    await ctx.dream_lite_run_repo.update_run(
        user_id=uid,
        lite_run_id=rid,
        patch={"step_phase": "anim_i2v", "gen_anim_i": 0, "last_error": None},
    )
    await callback.answer("Запускаю генерацию видео…")
    if callback.message:
        await resume_dream_lite_after_montage_confirm(
            message=callback.message,
            uid=uid,
            lite_run_id=rid,
            repo=ctx.dream_lite_run_repo,
            openai=ctx.openai,
            summary_repo=ctx.dream_lite_summary_repo,
            asset_repo=ctx.dream_lite_asset_repo,
        )
