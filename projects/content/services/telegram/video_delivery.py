"""Отправка mp4 в Telegram: метаданные под iOS (без изменения пайплайна генерации)."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from aiogram.types import FSInputFile, Message

logger = logging.getLogger(__name__)


def probe_video_dimensions(path: Path) -> tuple[int, int] | None:
    """Реальные width×height из файла (для width/height в sendVideo)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.is_file():
        return None
    try:
        r = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return None
        w = int(streams[0].get("width") or 0)
        h = int(streams[0].get("height") or 0)
        if w > 0 and h > 0:
            return w, h
    except Exception:
        logger.warning("probe_video_dimensions failed for %s", path, exc_info=True)
    return None


def remux_for_telegram_ios(path: Path) -> Path:
    """
    Лёгкий remux: SAR=1, faststart — только для отправки, исходник не трогаем.
    Если ffmpeg недоступен или ошибка — возвращает исходный path.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not path.is_file():
        return path
    fd, tmp_name = tempfile.mkstemp(prefix="tg_vid_", suffix=".mp4")
    os.close(fd)
    out = Path(tmp_name)
    try:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(path),
            "-vf",
            "setsar=1",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
        if r.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            return out
        logger.warning(
            "remux_for_telegram_ios failed rc=%s: %s",
            r.returncode,
            (r.stderr or "")[-500:],
        )
        out.unlink(missing_ok=True)
    except Exception:
        logger.warning("remux_for_telegram_ios error", exc_info=True)
        out.unlink(missing_ok=True)
    return path


async def answer_video_file(
    message: Message,
    path: Path,
    *,
    caption: str | None = None,
    reply_markup: object | None = None,
    remux_ios: bool = False,
) -> None:
    """
    Отправка локального mp4: width/height из файла (важно для iOS Telegram).
    Опционально remux_ios — перекод только перед отправкой, пайплайн не трогает.
    Fallback — document, если sendVideo не прошёл.
    """
    send_path = remux_for_telegram_ios(path) if remux_ios else path
    cleanup = send_path != path
    dims = probe_video_dimensions(send_path)
    kw: dict = {
        "caption": caption,
        "supports_streaming": True,
    }
    if reply_markup is not None:
        kw["reply_markup"] = reply_markup
    if dims:
        kw["width"], kw["height"] = dims

    try:
        await message.answer_video(video=FSInputFile(send_path), **kw)
        return
    except Exception:
        logger.warning("answer_video failed, try document", exc_info=True)
    try:
        await message.answer_document(
            document=FSInputFile(send_path),
            caption=caption,
        )
    finally:
        if cleanup:
            send_path.unlink(missing_ok=True)
