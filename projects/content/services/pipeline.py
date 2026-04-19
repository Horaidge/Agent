"""Оркестрация: LLM → изображение → анимация → пути к артефактам."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config.settings import Settings
from services.animation.animator import Animator
from services.images.generator import ImageGenerator
from services.llm.client import LlmClient


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Результат одного прогона пайплайна (для логов и ответа пользователю)."""

    work_dir: Path
    prompt_refined: str | None
    image_path: Path | None
    video_path: Path | None


class ContentPipeline:
    """Связывает этапы; реализации сервисов подставляются снаружи."""

    def __init__(
        self,
        settings: Settings,
        llm: LlmClient,
        images: ImageGenerator,
        animation: Animator,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._images = images
        self._animation = animation

    async def run(self, user_text: str, job_id: str) -> PipelineResult:
        """
        Заглушка: после реализации LlmClient / ImageGenerator / Animator
        создавайте подпапку в data/temp и складывайте туда файлы.
        """
        base = self._settings.data_dir / "temp" / job_id
        base.mkdir(parents=True, exist_ok=True)
        _ = user_text
        return PipelineResult(
            work_dir=base,
            prompt_refined=None,
            image_path=None,
            video_path=None,
        )
