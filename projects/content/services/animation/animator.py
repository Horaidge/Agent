"""Анимация статичного изображения в видео (FFmpeg, внешний сервис и т.д.)."""
from __future__ import annotations

from pathlib import Path


class Animator:
    """Превращение изображения в короткое видео."""

    async def animate(self, image_path: Path, out_video_path: Path) -> Path:
        raise NotImplementedError
