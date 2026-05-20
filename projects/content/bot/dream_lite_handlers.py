"""Команды Telegram: Dream Pipeline Lite до финального mp4."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.config.settings import get_settings
from services.dreams.dream_lite_telegram_runner import (
    resume_dream_lite_after_montage_confirm,
    run_dream_lite_for_telegram_user,
)
from services.observability.dream_pipeline_lite import lite_fs_path_from_dev_static_url
from services.dreams.dream_orchestrator import DreamPipelineService
from services.telegram_reply_keyboards import main_reply_keyboard
from storage.dream_lite_asset_repository import DreamLiteAssetRepository
from storage.dream_lite_run_repository import DreamLiteRunRepository
from storage.dream_lite_summary_repository import DreamLiteSummaryRepository

router = Router(name="dream_lite_telegram")


async def _safe_callback_answer(callback: CallbackQuery, text: str | None = None, *, show_alert: bool = False) -> None:
    try:
        if text is None:
            await callback.answer()
        else:
            await callback.answer(text, show_alert=show_alert)
    except Exception:
        return


async def _safe_callback_edit_text(callback: CallbackQuery, text: str, *, reply_markup: InlineKeyboardMarkup | None = None) -> bool:
    if callback.message is None:
        return False
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
        return True
    except Exception:
        return False


@router.message(Command("dreamlite", "lite"))
async def on_dream_lite_command(
    message: Message,
    command: CommandObject,
    dream_lite_run_repo: DreamLiteRunRepository | None,
    dream_lite_summary_repo: DreamLiteSummaryRepository | None,
    dream_lite_asset_repo: DreamLiteAssetRepository | None,
    dream_pipeline_service: DreamPipelineService | None,
) -> None:
    raw = (command.args or "").strip()
    if not raw:
        await message.answer(
            "Укажи текст сна после команды, например:\n"
            "/dreamlite Я шёл по коридору и увидел вертолёт\n\n"
            "Будут шаги: персонажи → окружения → кадры → план монтажа → i2v → склейка mp4.",
            reply_markup=main_reply_keyboard(),
        )
        return

    if dream_lite_run_repo is None:
        await message.answer(
            "Dream Lite (Mongo run) не подключён на сервере.",
            reply_markup=main_reply_keyboard(),
        )
        return

    openai = getattr(dream_pipeline_service, "_openai", None) if dream_pipeline_service else None
    if not openai or not getattr(openai, "configured", False):
        await message.answer(
            "LLM для Dream Lite не сконфигурирован (нужен рабочий OpenAI/OpenRouter клиент в dream pipeline).",
            reply_markup=main_reply_keyboard(),
        )
        return

    await run_dream_lite_for_telegram_user(
        message=message,
        dream_text=raw,
        repo=dream_lite_run_repo,
        openai=openai,
        summary_repo=dream_lite_summary_repo,
        asset_repo=dream_lite_asset_repo,
    )


@router.callback_query(F.data.startswith("dlmc:"))
async def on_dream_lite_montage_confirm(
    callback: CallbackQuery,
    dream_lite_run_repo: DreamLiteRunRepository | None,
    dream_lite_summary_repo: DreamLiteSummaryRepository | None,
    dream_lite_asset_repo: DreamLiteAssetRepository | None,
    dream_pipeline_service: DreamPipelineService | None,
) -> None:
    if dream_lite_run_repo is None:
        await callback.answer("Dream Lite недоступен.", show_alert=True)
        return
    uid = callback.from_user.id if callback.from_user else 0
    rid = (callback.data or "").split(":", 1)[1].strip()
    doc = await dream_lite_run_repo.get_run(user_id=uid, lite_run_id=rid)
    if not doc or str(doc.get("step_phase") or "") != "montage_confirm":
        await callback.answer("Запуск устарел или уже подтверждён.", show_alert=True)
        return
    await dream_lite_run_repo.update_run(
        user_id=uid,
        lite_run_id=rid,
        patch={
            "step_phase": "anim_i2v",
            "gen_anim_i": 0,
            "last_error": None,
        },
    )
    await callback.answer("Запускаю генерацию видео…")
    openai = getattr(dream_pipeline_service, "_openai", None) if dream_pipeline_service else None
    if not openai or not getattr(openai, "configured", False):
        if callback.message:
            await callback.message.answer(
                "LLM для Dream Lite не сконфигурирован.",
                reply_markup=main_reply_keyboard(),
            )
        return
    if callback.message:
        await resume_dream_lite_after_montage_confirm(
            message=callback.message,
            uid=uid,
            lite_run_id=rid,
            repo=dream_lite_run_repo,
            openai=openai,
            summary_repo=dream_lite_summary_repo,
            asset_repo=dream_lite_asset_repo,
        )


def _dreams_list_keyboard(items: list[dict[str, object]], offset: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for it in items:
        rid = str(it.get("lite_run_id") or "").strip()
        if not rid:
            continue
        title = str(it.get("title") or it.get("dream_excerpt") or rid[:8]).strip()
        status = str(it.get("run_status") or "unknown").strip()
        label = f"{title[:36]} · {status}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"dlh:op:{rid}")])
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"dlh:ls:{max(0, offset - 10)}"))
    if len(items) >= 10:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"dlh:ls:{offset + 10}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="Пусто", callback_data="dlh:none:0")]])


@router.message(Command("mydreams"))
async def on_dream_lite_history(
    message: Message,
    dream_lite_run_repo: DreamLiteRunRepository | None,
    dream_lite_summary_repo: DreamLiteSummaryRepository | None,
) -> None:
    uid = message.from_user.id if message.from_user else 0
    if uid <= 0:
        await message.answer("Не удалось определить пользователя.", reply_markup=main_reply_keyboard())
        return
    if dream_lite_run_repo is None:
        await message.answer("Dream Lite не подключён.", reply_markup=main_reply_keyboard())
        return
    if dream_lite_summary_repo is not None:
        items = dream_lite_summary_repo.list_user_summaries_sync(user_id=uid, limit=10, offset=0)
    else:
        items = dream_lite_run_repo.list_recent_runs_sync(limit=10, user_id=uid)
    if not items:
        await message.answer("У вас пока нет сохранённых снов Dream Lite.", reply_markup=main_reply_keyboard())
        return
    await message.answer("Ваши последние сны Dream Lite:", reply_markup=_dreams_list_keyboard(items, 0))


@router.callback_query(F.data.startswith("dlh:"))
async def on_dream_lite_history_callbacks(
    callback: CallbackQuery,
    dream_lite_run_repo: DreamLiteRunRepository | None,
    dream_lite_summary_repo: DreamLiteSummaryRepository | None,
    dream_lite_asset_repo: DreamLiteAssetRepository | None,
) -> None:
    if dream_lite_run_repo is None:
        await callback.answer("Dream Lite недоступен.", show_alert=True)
        return
    uid = callback.from_user.id if callback.from_user else 0
    if uid <= 0:
        await callback.answer("user not found", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "none":
        await _safe_callback_answer(callback)
        return
    if action == "ls":
        off = int(parts[2]) if len(parts) > 2 and str(parts[2]).isdigit() else 0
        if dream_lite_summary_repo is not None:
            items = dream_lite_summary_repo.list_user_summaries_sync(user_id=uid, limit=10, offset=off)
        else:
            items = dream_lite_run_repo.list_recent_runs_sync(limit=10, user_id=uid)
        if callback.message:
            await _safe_callback_edit_text(
                callback,
                "Ваши последние сны Dream Lite:",
                reply_markup=_dreams_list_keyboard(items, off),
            )
        await _safe_callback_answer(callback)
        return
    if action == "op":
        rid = parts[2] if len(parts) > 2 else ""
        run = await dream_lite_run_repo.get_run(user_id=uid, lite_run_id=rid)
        if not run:
            await callback.answer("Сон не найден.", show_alert=True)
            return
        frames_count = len(list(run.get("generated_frames") or []))
        final_video = str(run.get("final_video_url") or "").strip()
        txt = (
            f"Сон: {str(run.get('dream_text') or '')[:700]}\n\n"
            f"Run: {rid}\n"
            f"Статус: {run.get('run_status')} · Фаза: {run.get('step_phase')}\n"
            f"Кадров: {frames_count}\n"
            f"Видео: {'да' if final_video else 'нет'}"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Показать кадры", callback_data=f"dlh:fr:{rid}")],
                [InlineKeyboardButton(text="Показать видео", callback_data=f"dlh:vd:{rid}")],
                [InlineKeyboardButton(text="К списку", callback_data="dlh:ls:0")],
            ]
        )
        if callback.message:
            await _safe_callback_edit_text(callback, txt[:3500], reply_markup=kb)
        await _safe_callback_answer(callback)
        return
    if action == "fr":
        rid = parts[2] if len(parts) > 2 else ""
        assets = (
            dream_lite_asset_repo.list_assets_sync(user_id=uid, lite_run_id=rid, asset_kind="frame", limit=8)
            if dream_lite_asset_repo is not None
            else []
        )
        if not assets:
            run = await dream_lite_run_repo.get_run(user_id=uid, lite_run_id=rid)
            if run:
                for fr in list(run.get("generated_frames") or [])[:8]:
                    for u in list((fr or {}).get("urls") or [])[:1]:
                        assets.append({"public_url": str(u or "").strip(), "asset_index": int((fr or {}).get("index") or 0)})
        if not assets:
            await _safe_callback_answer(callback, "Кадры не найдены.", show_alert=True)
            return
        if callback.message:
            await callback.message.answer("Отправляю кадры сна…", reply_markup=main_reply_keyboard())
        cfg = get_settings()
        base = (cfg.public_base_url or "").strip().rstrip("/")
        for a in assets:
            raw_u = str(a.get("public_url") or "").strip()
            if not raw_u:
                continue
            try:
                if raw_u.startswith("/dev/static/"):
                    p = lite_fs_path_from_dev_static_url(raw_u)
                    if p and p.is_file():
                        await callback.message.answer_photo(photo=FSInputFile(p))
                        continue
                    if base:
                        await callback.message.answer_photo(photo=f"{base}{raw_u}")
                        continue
                await callback.message.answer_photo(photo=raw_u)
            except Exception:
                continue
        await _safe_callback_answer(callback)
        return
    if action == "vd":
        rid = parts[2] if len(parts) > 2 else ""
        video_url = ""
        if dream_lite_asset_repo is not None:
            assets = dream_lite_asset_repo.list_assets_sync(
                user_id=uid,
                lite_run_id=rid,
                asset_kind="final_video",
                limit=1,
            )
            if assets:
                video_url = str(assets[0].get("public_url") or "").strip()
        if not video_url:
            run = await dream_lite_run_repo.get_run(user_id=uid, lite_run_id=rid)
            video_url = str((run or {}).get("final_video_url") or "").strip()
        if not video_url:
            await _safe_callback_answer(callback, "Финальное видео не найдено.", show_alert=True)
            return
        try:
            cfg = get_settings()
            base = (cfg.public_base_url or "").strip().rstrip("/")
            if video_url.startswith("/dev/static/"):
                p = lite_fs_path_from_dev_static_url(video_url)
                if p and p.is_file():
                    await callback.message.answer_video(video=FSInputFile(p), caption="Финальное видео Dream Lite")
                elif base:
                    await callback.message.answer_video(video=f"{base}{video_url}", caption="Финальное видео Dream Lite")
                else:
                    await callback.message.answer(f"Видео доступно по пути: {video_url}")
            else:
                await callback.message.answer_video(video=video_url, caption="Финальное видео Dream Lite")
        except Exception:
            await callback.message.answer(f"Не удалось отправить видео. URL: {video_url}")
        await _safe_callback_answer(callback)
        return
    await _safe_callback_answer(callback)
