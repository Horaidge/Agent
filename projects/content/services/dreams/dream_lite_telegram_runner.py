"""Telegram: полный Dream Pipeline Lite (Mongo run) до финального mp4 и отправка пользователю."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.config.settings import Settings, get_settings
from services.observability.dream_lite_metrics_store import record_metric
from services.observability.dream_lite_run_worker import process_dream_lite_run_step
from services.observability.dream_pipeline_lite import lite_fs_path_from_dev_static_url
from services.telegram_reply_keyboards import main_reply_keyboard
from services.telegram.video_delivery import answer_video_file
from storage.dream_lite_asset_repository import DreamLiteAssetRepository
from storage.dream_lite_run_repository import DreamLiteRunRepository
from storage.dream_lite_summary_repository import DreamLiteSummaryRepository

logger = logging.getLogger(__name__)

_MAX_STEPS = 8000


def _montage_confirm_summary(doc: dict[str, Any]) -> str:
    rc = doc.get("run_config") if isinstance(doc.get("run_config"), dict) else {}
    vp = rc.get("video_policy") if isinstance(rc.get("video_policy"), dict) else {}
    plan = doc.get("transition_plan") or {}
    trans = [
        t
        for t in (plan.get("transitions") or [])
        if isinstance(t, dict) and str(t.get("transition_type") or "") == "animate_transition"
    ]
    dur = vp.get("duration_sec")
    res = vp.get("resolution")
    stride = vp.get("scene_segment_stride")
    lines = [
        "План монтажа готов. Ниже — что пойдёт в генерацию видео.",
        f"Сегментов animate_transition: {len(trans)}",
        f"Настройки клипа: {dur}s · {res}"
        + (f" · stride сцен={stride}" if stride and int(stride) > 1 else ""),
    ]
    for i, t in enumerate(trans[:14]):
        mp = str(t.get("motion_prompt") or "").strip()
        if len(mp) > 100:
            mp = mp[:97] + "…"
        lines.append(
            f"  {i + 1}. кадры {t.get('from_frame_index')}→{t.get('to_frame_index')}: {mp or '—'}"
        )
    if len(trans) > 14:
        lines.append(f"  … и ещё {len(trans) - 14}")
    lines.append("")
    lines.append("Подтверди кнопкой ниже — запущу i2v.")
    return "\n".join(lines)


async def _dream_lite_drive_pipeline_loop(
    *,
    uid: int,
    lite_run_id: str,
    repo: DreamLiteRunRepository,
    openai: Any,
    status: Message,
    break_on_montage_confirm: bool,
    summary_repo: DreamLiteSummaryRepository | None = None,
    asset_repo: DreamLiteAssetRepository | None = None,
) -> tuple[dict[str, Any], bool]:
    """
    Один цикл process_dream_lite_run_step до done / ошибки / (опционально) montage_confirm.
    Возвращает (last_out, stopped_at_montage_confirm).
    """
    last_out: dict[str, Any] = {}
    last_phase = ""
    steps = 0
    stopped_mc = False
    while steps < _MAX_STEPS:
        steps += 1
        out = await process_dream_lite_run_step(
            repo=repo,
            openai=openai,
            user_id=uid,
            lite_run_id=lite_run_id,
            summary_repo=summary_repo,
            asset_repo=asset_repo,
        )
        await _sync_dream_lite_history_views(
            repo=repo,
            user_id=uid,
            lite_run_id=lite_run_id,
            summary_repo=summary_repo,
            asset_repo=asset_repo,
        )
        last_out = out
        if not out.get("ok"):
            return out, False

        ph = str(
            out.get("step_phase")
            or out.get("next_phase")
            or out.get("step")
            or "",
        )
        if ph and ph != last_phase:
            last_phase = ph
            try:
                await status.edit_text(_phase_status_text(last_phase))
            except Exception:
                pass

        if break_on_montage_confirm and out.get("await_montage_confirm"):
            stopped_mc = True
            break
        if out.get("done"):
            break
    else:
        last_out = dict(last_out or {})
        last_out["ok"] = False
        last_out["error"] = last_out.get("error") or "step_limit"
        return last_out, False

    return last_out, stopped_mc


async def _dream_lite_deliver_final_video(
    *,
    message: Message,
    status: Message,
    uid: int,
    lite_run_id: str,
    repo: DreamLiteRunRepository,
    cfg: Settings,
    last_out: dict[str, Any],
    summary_repo: DreamLiteSummaryRepository | None = None,
    asset_repo: DreamLiteAssetRepository | None = None,
) -> None:
    doc = await repo.get_run(user_id=uid, lite_run_id=lite_run_id) or {}
    final_url = doc.get("final_video_url") or last_out.get("final_video_url")
    asm_err = doc.get("final_assembly_error") or last_out.get("final_assembly_error")

    if final_url:
        path = lite_fs_path_from_dev_static_url(str(final_url))
        if path and path.is_file():
            try:
                await answer_video_file(
                    message,
                    path,
                    caption="Dream Lite: готово.",
                    reply_markup=main_reply_keyboard(),
                )
                await _safe_status_edit(status, "Dream Lite: готово — видео отправлено.")
                logger.info(
                    "dream_lite delivery_event user_id=%s run=%s channel=telegram method=local_file status=ok",
                    uid,
                    lite_run_id,
                )
                record_metric({"stage": "delivery", "user_id": int(uid), "lite_run_id": str(lite_run_id), "status": "ok", "method": "local_file"})
                await repo.update_run(
                    user_id=uid,
                    lite_run_id=lite_run_id,
                    patch={"last_delivery_status": "telegram_video_sent_local_file"},
                )
                await _sync_dream_lite_history_views(
                    repo=repo,
                    user_id=uid,
                    lite_run_id=lite_run_id,
                    summary_repo=summary_repo,
                    asset_repo=asset_repo,
                )
                return
            except Exception:
                logger.exception("dream_lite telegram: отправка файла не удалась")

        base = (cfg.public_base_url or "").strip().rstrip("/")
        if base:
            full_video = f"{base}{final_url}"
            downloaded = await asyncio.to_thread(_download_video_for_telegram, full_video)
            if downloaded and downloaded.is_file():
                try:
                    await answer_video_file(
                        message,
                        downloaded,
                        caption="Dream Lite: готово.",
                        reply_markup=main_reply_keyboard(),
                    )
                    await _safe_status_edit(status, "Dream Lite: готово — видео скачано и отправлено.")
                    logger.info(
                        "dream_lite delivery_event user_id=%s run=%s channel=telegram method=downloaded_file status=ok",
                        uid,
                        lite_run_id,
                    )
                    record_metric({"stage": "delivery", "user_id": int(uid), "lite_run_id": str(lite_run_id), "status": "ok", "method": "downloaded_file"})
                    await repo.update_run(
                        user_id=uid,
                        lite_run_id=lite_run_id,
                        patch={"last_delivery_status": "telegram_video_sent_downloaded_file"},
                    )
                    await _sync_dream_lite_history_views(
                        repo=repo,
                        user_id=uid,
                        lite_run_id=lite_run_id,
                        summary_repo=summary_repo,
                        asset_repo=asset_repo,
                    )
                    return
                except Exception:
                    logger.exception("dream_lite telegram: отправка скачанного видео не удалась")
                finally:
                    downloaded.unlink(missing_ok=True)
            try:
                await message.answer_video(
                    video=full_video,
                    caption="Dream Lite: готово.",
                    supports_streaming=True,
                    reply_markup=main_reply_keyboard(),
                )
                await _safe_status_edit(status, "Dream Lite: готово — видео по публичному URL.")
                logger.info(
                    "dream_lite delivery_event user_id=%s run=%s channel=telegram method=public_url status=ok",
                    uid,
                    lite_run_id,
                )
                record_metric({"stage": "delivery", "user_id": int(uid), "lite_run_id": str(lite_run_id), "status": "ok", "method": "public_url"})
                await repo.update_run(
                    user_id=uid,
                    lite_run_id=lite_run_id,
                    patch={"last_delivery_status": "telegram_video_sent_public_url"},
                )
                await _sync_dream_lite_history_views(
                    repo=repo,
                    user_id=uid,
                    lite_run_id=lite_run_id,
                    summary_repo=summary_repo,
                    asset_repo=asset_repo,
                )
                return
            except Exception:
                logger.exception("dream_lite telegram: отправка по URL не удалась")

    err_tail = f" Сборка: {asm_err}" if asm_err else ""
    updated = await _safe_status_edit(
        status,
        "Dream Lite: пайплайн завершён, но итогового видео нет." + err_tail,
    )
    if not updated:
        await message.answer(
            ("Dream Lite: пайплайн завершён, но итогового видео нет." + err_tail)[:3500],
            reply_markup=main_reply_keyboard(),
        )
    if final_url:
        await message.answer(
            f"Путь на сервере (если бот не смог отправить файл): {final_url}",
            reply_markup=main_reply_keyboard(),
        )
    await repo.update_run(
        user_id=uid,
        lite_run_id=lite_run_id,
        patch={"last_delivery_status": "telegram_video_delivery_failed"},
    )
    logger.warning(
        "dream_lite delivery_event user_id=%s run=%s channel=telegram method=all status=failed",
        uid,
        lite_run_id,
    )
    record_metric({"stage": "delivery", "user_id": int(uid), "lite_run_id": str(lite_run_id), "status": "failed", "method": "all"})
    await _sync_dream_lite_history_views(
        repo=repo,
        user_id=uid,
        lite_run_id=lite_run_id,
        summary_repo=summary_repo,
        asset_repo=asset_repo,
    )


async def resume_dream_lite_after_montage_confirm(
    *,
    message: Message,
    uid: int,
    lite_run_id: str,
    repo: DreamLiteRunRepository,
    openai: Any,
    settings: Settings | None = None,
    summary_repo: DreamLiteSummaryRepository | None = None,
    asset_repo: DreamLiteAssetRepository | None = None,
) -> None:
    """После callback: докрутить anim_i2v → финал."""
    cfg = settings or get_settings()
    status = await message.answer(
        "Dream Lite: продолжаю генерацию видео…",
        reply_markup=main_reply_keyboard(),
    )
    last_out, _ = await _dream_lite_drive_pipeline_loop(
        uid=uid,
        lite_run_id=lite_run_id,
        repo=repo,
        openai=openai,
        status=status,
        break_on_montage_confirm=False,
        summary_repo=summary_repo,
        asset_repo=asset_repo,
    )
    if not last_out.get("ok"):
        err = str(last_out.get("error") or "unknown")
        await _safe_status_edit(
            status,
            "Dream Lite: не удалось завершить пайплайн после подтверждения.",
        )
        await message.answer(f"Ошибка: {err[:800]}", reply_markup=main_reply_keyboard())
        return
    await _dream_lite_deliver_final_video(
        message=message,
        status=status,
        uid=uid,
        lite_run_id=lite_run_id,
        repo=repo,
        cfg=cfg,
        last_out=last_out,
        summary_repo=summary_repo,
        asset_repo=asset_repo,
    )
_MIN_SECONDS_BETWEEN_RUNS = 45
_FAILED_RUN_COOLDOWN_SECONDS = 300
_ACTIVE_RUN_STALE_SECONDS = 900


def _download_video_for_telegram(url: str) -> Path | None:
    """
    Скачивает публичный mp4 во временный файл, чтобы отправить как FSInputFile.
    Это надёжнее для Telegram, чем отдавать длинный presigned URL напрямую.
    """
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return None
    fd, tmp_name = tempfile.mkstemp(prefix="dream_lite_", suffix=".mp4")
    try:
        with urllib.request.urlopen(u, timeout=45) as resp, os.fdopen(fd, "wb") as f:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
        return Path(tmp_name)
    except Exception:
        logger.exception("dream_lite telegram: download video failed: %s", u)
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except Exception:
            pass
        return None


async def _safe_status_edit(status: Message, text: str) -> bool:
    """Обновляет статус, не роняя раннер на TelegramBadRequest."""
    try:
        await status.edit_text(text[:3500])
        return True
    except Exception:
        logger.warning("dream_lite telegram: status.edit_text failed", exc_info=True)
        return False


def _phase_status_text(phase: str) -> str:
    p = (phase or "").strip().lower()
    if p == "text_step1":
        return "Dream Lite: сон принят, подготавливаю окружения и персонажей…"
    if p == "text_step2":
        return "Dream Lite: строю раскадровку…"
    if p in ("gen_env", "gen_char", "gen_frame"):
        return "Dream Lite: генерирую изображения…"
    if p == "transition_plan":
        return "Dream Lite: подготавливаю план анимации…"
    if p == "montage_confirm":
        return "Dream Lite: жду подтверждения плана монтажа…"
    if p == "anim_i2v":
        return "Dream Lite: анимирую сцены…"
    if p == "finalize_clips":
        return "Dream Lite: собираю финальное видео…"
    if p == "completed":
        return "Dream Lite: готово."
    return "Dream Lite: выполняю шаги пайплайна…"


async def run_dream_lite_for_telegram_user(
    *,
    message: Message,
    dream_text: str,
    repo: DreamLiteRunRepository,
    openai: Any,
    settings: Settings | None = None,
    summary_repo: DreamLiteSummaryRepository | None = None,
    asset_repo: DreamLiteAssetRepository | None = None,
) -> str | None:
    cfg = settings or get_settings()
    uid = message.from_user.id if message.from_user else 0
    if uid <= 0:
        await message.answer(
            "Не удалось определить пользователя Telegram.",
            reply_markup=main_reply_keyboard(),
        )
        return None

    await _dream_lite_retention_maintenance(
        repo=repo,
        asset_repo=asset_repo,
    )

    try:
        stale_failed = await repo.fail_stale_active_runs(
            user_id=uid,
            max_idle_seconds=_ACTIVE_RUN_STALE_SECONDS,
            reason="auto_fail_stale_active_run",
        )
        if stale_failed:
            logger.warning("dream_lite: auto-failed stale active runs user_id=%s count=%s", uid, stale_failed)
    except Exception:
        logger.warning("dream_lite: stale active run cleanup failed", exc_info=True)

    recent_runs = await asyncio.to_thread(repo.list_recent_runs_sync, user_id=uid, limit=20)
    has_active = any(str(r.get("run_status") or "").strip().lower() == "active" for r in recent_runs)
    if has_active:
        await message.answer(
            "Dream Lite уже выполняется для этого пользователя. "
            "Дождитесь завершения текущего запуска.",
            reply_markup=main_reply_keyboard(),
        )
        return None

    latest = await repo.get_latest_run_for_user(user_id=uid)
    if latest:
        latest_status = str(latest.get("run_status") or "").strip().lower()
        latest_error = str(latest.get("last_error") or "").strip().lower()
        latest_updated = latest.get("updated_at")
        dt: datetime | None = None
        if isinstance(latest_updated, datetime):
            dt = latest_updated if latest_updated.tzinfo else latest_updated.replace(tzinfo=timezone.utc)
        elif latest_updated is not None:
            s = str(latest_updated).strip()
            if s:
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                try:
                    parsed = datetime.fromisoformat(s)
                    dt = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    dt = None
        now = datetime.now(timezone.utc)
        seconds_since = int((now - dt).total_seconds()) if dt else None

        stale_fail_marks = {
            "auto_fail_stale_active_run",
            "manual_fail_stale_active_run_from_dev_ui",
        }
        if (
            latest_status == "failed"
            and latest_error not in stale_fail_marks
            and seconds_since is not None
            and seconds_since < _FAILED_RUN_COOLDOWN_SECONDS
        ):
            wait_sec = _FAILED_RUN_COOLDOWN_SECONDS - seconds_since
            await message.answer(
                f"Предыдущий запуск завершился ошибкой. Повтор будет доступен через {wait_sec} сек.",
                reply_markup=main_reply_keyboard(),
            )
            return None

        if seconds_since is not None and seconds_since < _MIN_SECONDS_BETWEEN_RUNS:
            wait_sec = _MIN_SECONDS_BETWEEN_RUNS - seconds_since
            await message.answer(
                f"Слишком частый повтор запуска. Подождите {wait_sec} сек.",
                reply_markup=main_reply_keyboard(),
            )
            return None

    status = await message.answer(
        "Dream Lite: сон принят, запускаю полный пайплайн…",
        reply_markup=main_reply_keyboard(),
    )
    lite_run_id = await repo.create_run(user_id=uid, dream_text=dream_text.strip())
    await _sync_dream_lite_history_views(
        repo=repo,
        user_id=uid,
        lite_run_id=lite_run_id,
        summary_repo=summary_repo,
        asset_repo=asset_repo,
    )
    last_out: dict[str, Any] = {}

    try:
        last_out, stopped_mc = await _dream_lite_drive_pipeline_loop(
            uid=uid,
            lite_run_id=lite_run_id,
            repo=repo,
            openai=openai,
            status=status,
            break_on_montage_confirm=True,
            summary_repo=summary_repo,
            asset_repo=asset_repo,
        )
        if not last_out.get("ok"):
            err = str(last_out.get("error") or "unknown")
            await _safe_status_edit(
                status,
                "Dream Lite: не удалось завершить пайплайн. "
                "Ошибка сохранена в run; попробуйте ещё раз.",
            )
            await message.answer(
                f"Техническая причина: {err[:800]}",
                reply_markup=main_reply_keyboard(),
            )
            return lite_run_id

        if stopped_mc:
            doc_mc = await repo.get_run(user_id=uid, lite_run_id=lite_run_id) or {}
            summary = _montage_confirm_summary(doc_mc)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Подтвердить генерацию видео",
                            callback_data=f"dlmc:{lite_run_id}",
                        )
                    ]
                ]
            )
            await message.answer(summary[:3500], reply_markup=kb)
            await _safe_status_edit(status, _phase_status_text("montage_confirm"))
            return lite_run_id

        await _dream_lite_deliver_final_video(
            message=message,
            status=status,
            uid=uid,
            lite_run_id=lite_run_id,
            repo=repo,
            cfg=cfg,
            last_out=last_out,
            summary_repo=summary_repo,
            asset_repo=asset_repo,
        )
        return lite_run_id
    except Exception as exc:  # noqa: BLE001
        logger.exception("dream_lite telegram runner")
        try:
            await _safe_status_edit(
                status,
                "Dream Lite: внутренний сбой пайплайна. "
                "Ошибка сохранена, попробуйте повторить запуск."
            )
        except Exception:
            await message.answer(
                "Dream Lite: внутренний сбой пайплайна. Попробуйте повторить запуск.",
                reply_markup=main_reply_keyboard(),
            )
        return lite_run_id


async def _sync_dream_lite_history_views(
    *,
    repo: DreamLiteRunRepository,
    user_id: int,
    lite_run_id: str,
    summary_repo: DreamLiteSummaryRepository | None = None,
    asset_repo: DreamLiteAssetRepository | None = None,
) -> None:
    if summary_repo is None and asset_repo is None:
        return
    try:
        doc = await repo.get_run(user_id=user_id, lite_run_id=lite_run_id)
        if not doc:
            return
        if summary_repo is not None:
            await summary_repo.upsert_from_run_doc(doc)
        if asset_repo is not None:
            await asset_repo.upsert_from_run_doc(doc)
    except Exception:
        logger.warning("dream_lite history sync failed", exc_info=True)


async def _dream_lite_retention_maintenance(
    *,
    repo: DreamLiteRunRepository,
    asset_repo: DreamLiteAssetRepository | None,
) -> None:
    try:
        archived = await repo.mark_expired_runs_archived()
        if archived:
            logger.info("dream_lite retention: archived expired runs=%s", archived)
    except Exception:
        logger.warning("dream_lite retention: failed to archive expired runs", exc_info=True)
    if asset_repo is None:
        return
    try:
        urls = await asset_repo.purge_expired_assets()
        if not urls:
            return
        removed_files = 0
        for u in urls:
            if not str(u).startswith("/dev/static/"):
                continue
            p = lite_fs_path_from_dev_static_url(str(u))
            if p and p.is_file():
                p.unlink(missing_ok=True)
                removed_files += 1
        logger.info(
            "dream_lite retention: purged assets_docs=%s removed_local_files=%s",
            len(urls),
            removed_files,
        )
    except Exception:
        logger.warning("dream_lite retention: failed to purge expired assets", exc_info=True)
