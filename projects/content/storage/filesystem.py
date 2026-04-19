"""Пути к каталогам данных и простая подготовка структуры на диске."""
from __future__ import annotations

from pathlib import Path

from core.config.settings import Settings


def data_root(settings: Settings) -> Path:
    return settings.data_dir.resolve()


def ensure_data_dirs(settings: Settings) -> None:
    """Создаёт data/logs, data/temp, data/outputs при старте приложения."""
    root = data_root(settings)
    for sub in ("logs", "temp", "outputs", "runtime", "dev_uploads/video_inputs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
