"""Сущности dream-to-story-video (Pydantic)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage constants & progress tracking
# ---------------------------------------------------------------------------

class DreamStage:
    """Константы стадий Dream Pipeline для dream_runs.current_stage."""

    DECOMPOSING = "stage_1_decomposing"
    DECOMPOSED = "stage_1_complete"
    GENERATING_IMAGES = "stage_2_generating_images"
    IMAGES_COMPLETE = "stage_2_complete"
    ANIMATING = "stage_3_animating"
    ANIMATION_COMPLETE = "stage_3_complete"
    ASSEMBLING = "stage_4_assembling"
    COMPLETED = "completed"
    FAILED = "failed"


def _default_stage_progress() -> dict[str, Any]:
    return {
        "stage_1": {"status": "pending", "completed": 0, "total": 0},
        "stage_2": {"status": "pending", "completed": 0, "total": 0},
        "stage_3": {"status": "pending", "completed": 0, "total": 0},
        "stage_4": {"status": "pending", "completed": 0, "total": 0},
    }


class DreamStageProgress(BaseModel):
    """Персистентный прогресс всех стадий (хранится в dream_runs.stage_progress)."""

    current_stage: str = DreamStage.DECOMPOSING
    stages: dict[str, dict[str, Any]] = Field(default_factory=_default_stage_progress)

    def begin(self, stage_key: str, stage_const: str, total: int = 0) -> None:
        self.current_stage = stage_const
        self.stages[stage_key] = {"status": "in_progress", "completed": 0, "total": total}

    def tick(self, stage_key: str) -> None:
        self.stages[stage_key]["completed"] += 1

    def finish(self, stage_key: str, stage_const: str) -> None:
        self.current_stage = stage_const
        s = self.stages[stage_key]
        s["status"] = "complete"
        s["completed"] = s["total"]

    def fail(self, stage_key: str) -> None:
        self.current_stage = DreamStage.FAILED
        self.stages[stage_key]["status"] = "failed"


@dataclass
class SceneFrameData:
    """Результат Stage 2 для передачи в Stage 3."""

    scene_index: int
    scene: "DreamSceneItem"
    dream_scene_id: str
    frame_id: str
    image_url: str


# ---------------------------------------------------------------------------
# Scene / plan models
# ---------------------------------------------------------------------------

class DreamSceneOutline(BaseModel):
    """Сцена после шага 1 — только смысл и метаданные, без промптов картинки/видео."""

    scene_index: int = Field(ge=1)
    title: str = ""
    short_description: str = ""
    scene_description: str = ""
    character_requirement: str = "main_character"
    environment_requirement: str = ""
    mood: str = ""
    duration_sec: int = Field(default=4, ge=2, le=15)
    camera_motion: bool = False


class DreamSceneItem(BaseModel):
    """Один смысловой кадр / сцена — полный план после всех LLM-шагов."""

    scene_index: int = Field(ge=1)
    title: str = ""
    short_description: str = ""
    scene_description: str = ""
    visual_prompt: str = ""
    # Шаг 2 pipeline: base_character | face | none (пусто = авто как раньше)
    reference_type: str = ""
    character_requirement: str = "main_character"
    environment_requirement: str = ""
    mood: str = ""
    animation_prompt: str = ""
    duration_sec: int = Field(default=4, ge=2, le=15)
    camera_motion: bool = False


class DreamScenePlan(BaseModel):
    """Полный план сцен (ответ LLM)."""

    scenes: list[DreamSceneItem] = Field(default_factory=list)
    dream_summary: str = ""


class DreamRunPublicState(BaseModel):
    """Упрощённое состояние для UI / логов."""

    run_id: str | None = None
    trace_id: str = ""
    status: str = ""
    scene_count: int = 0
    error: str | None = None
