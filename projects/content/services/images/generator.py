"""Генерация изображений через внешний API или локальный рантайм."""
from __future__ import annotations

from pathlib import Path


class ImageGenerator:
    """Создание изображений по текстовому промпту; результат — файл на диске."""

    async def generate(self, prompt: str, out_path: Path) -> Path:
        raise NotImplementedError
