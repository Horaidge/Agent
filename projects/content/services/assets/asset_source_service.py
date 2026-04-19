"""
Подготовка изображения для Wan image-to-video из dream_assets или локального файла.

DashScope принимает публичный URL или data URI (`img_url` в API). Telegram `file_id`
сначала скачивается через Bot API, затем кодируется в data URI (без публичного URL).
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Ограничение спецификации image-to-video (Alibaba)
_MAX_IMAGE_BYTES = 10 * 1024 * 1024

_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
}


class AssetSourceError(Exception):
    """Не удалось получить байты изображения или слишком большой файл."""


def bytes_to_data_uri(content: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.standard_b64encode(content).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _mime_for_path(path: Path) -> str:
    return _EXT_TO_MIME.get(path.suffix.lower(), "image/jpeg")


def load_local_file_as_data_uri(path: Path) -> tuple[str, dict[str, Any]]:
    """Читает локальный файл → data URI + метаданные для video_jobs.extra."""
    p = path.expanduser().resolve()
    if not p.is_file():
        raise AssetSourceError(f"Файл не найден: {p}")
    raw = p.read_bytes()
    if len(raw) > _MAX_IMAGE_BYTES:
        raise AssetSourceError(
            f"Изображение слишком большое ({len(raw)} B), максимум {_MAX_IMAGE_BYTES} B"
        )
    mime = _mime_for_path(p)
    uri = bytes_to_data_uri(raw, mime)
    meta = {
        "source_type": "dev_upload",
        "source_label": p.name,
        "dev_upload_path": str(p),
    }
    return uri, meta


def download_telegram_file_bytes(bot_token: str, file_id: str) -> tuple[bytes, str]:
    """Скачивает файл по Telegram file_id, возвращает (bytes, mime)."""
    if not bot_token.strip():
        raise AssetSourceError("Не задан TELEGRAM_BOT_TOKEN для скачивания file_id")
    base = f"https://api.telegram.org/bot{bot_token.strip()}"
    with httpx.Client(timeout=120.0) as client:
        gr = client.get(f"{base}/getFile", params={"file_id": file_id})
        gr.raise_for_status()
        body = gr.json()
        if not body.get("ok"):
            raise AssetSourceError(f"getFile: {body!r}")
        result = body.get("result") or {}
        file_path = result.get("file_path")
        if not file_path:
            raise AssetSourceError("getFile: нет file_path")
        fu = f"https://api.telegram.org/file/bot{bot_token.strip()}/{file_path}"
        fr = client.get(fu)
        fr.raise_for_status()
        content = fr.content
    if len(content) > _MAX_IMAGE_BYTES:
        raise AssetSourceError(
            f"Файл Telegram слишком большой ({len(content)} B), максимум {_MAX_IMAGE_BYTES} B"
        )
    ext = Path(str(file_path)).suffix.lower()
    mime = _EXT_TO_MIME.get(ext, "image/jpeg")
    return content, mime


def dream_asset_to_data_uri(
    asset: dict[str, Any],
    *,
    bot_token: str,
) -> tuple[str, dict[str, Any]]:
    """
    dream_assets документ с telegram_file_id → data URI для Wan API.

    Возвращает (data_uri, extra для video_jobs).
    """
    fid = asset.get("telegram_file_id")
    if not fid:
        raise AssetSourceError("У asset нет telegram_file_id")
    raw, mime = download_telegram_file_bytes(bot_token, str(fid))
    uri = bytes_to_data_uri(raw, mime)
    oid = asset.get("_id")
    meta = {
        "source_type": "dream_asset",
        "source_label": f"asset {oid}",
        "dream_asset_id": str(oid) if oid is not None else None,
        "dream_owner_user_id": asset.get("owner_user_id"),
    }
    logger.info(
        "asset_source: dream_asset %s → data URI (image %s B)",
        oid,
        len(raw),
    )
    return uri, meta
