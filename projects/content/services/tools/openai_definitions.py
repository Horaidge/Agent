"""
Реестр инструментов для OpenAI Chat Completions (function calling).

Источник истины по каждому инструменту лежит в `services/tools/model_tools/*`:
- schema (что видит модель),
- описание,
- правила аргументов.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.tools.model_tools.generate_image_tool import (
    OPENAI_TOOL_SCHEMA as GENERATE_IMAGE_TOOL,
)
from services.tools.model_tools.generate_image_openrouter_tool import (
    OPENAI_TOOL_SCHEMA as GENERATE_IMAGE_OPENROUTER_TOOL,
)
from services.tools.model_tools.dream_pipeline_tool import (
    OPENAI_TOOL_SCHEMA as DREAM_PIPELINE_TOOL,
)
from services.tools.model_tools.check_dream_pipeline_health_tool import (
    OPENAI_TOOL_SCHEMA as DREAM_PIPELINE_HEALTH_TOOL,
)
from services.tools.model_tools.image_to_video_tool import (
    OPENAI_TOOL_SCHEMA as IMAGE_TO_VIDEO_TOOL,
)
from services.tools.model_tools.video_trim_start_tool import (
    OPENAI_TOOL_SCHEMA as VIDEO_TRIM_START_TOOL,
)
from services.tools.model_tools.last_frame_reference_tool import (
    OPENAI_TOOL_SCHEMA as LAST_FRAME_AS_REFERENCE_TOOL,
)
from services.tools.model_tools.concat_video_clips_tool import (
    OPENAI_TOOL_SCHEMA as CONCAT_VIDEO_CLIPS_TOOL,
)

# Список tools, передаваемых в chat по умолчанию (расширяйте по мере добавления схем выше)
OPENAI_TOOLS_DEFAULT: list[dict[str, Any]] = [
    DREAM_PIPELINE_TOOL,
    DREAM_PIPELINE_HEALTH_TOOL,
]

# Полный каталог доступных описаний (включая неактивные по умолчанию)
OPENAI_TOOLS_CATALOG: list[dict[str, Any]] = [
    GENERATE_IMAGE_TOOL,
    GENERATE_IMAGE_OPENROUTER_TOOL,
    DREAM_PIPELINE_TOOL,
    DREAM_PIPELINE_HEALTH_TOOL,
    IMAGE_TO_VIDEO_TOOL,
    CONCAT_VIDEO_CLIPS_TOOL,
    VIDEO_TRIM_START_TOOL,
    LAST_FRAME_AS_REFERENCE_TOOL,
]


def _tool_name(schema: dict[str, Any]) -> str:
    fn = (schema.get("function") or {}).get("name")
    return str(fn or "").strip()


def _overrides_path(data_dir: Path) -> Path:
    return (data_dir / "runtime" / "dev_tool_overrides.json").resolve()


def _load_enabled_from_overrides(data_dir: Path) -> dict[str, bool]:
    path = _overrides_path(data_dir)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, bool] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        enabled = value.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes")
        out[key] = bool(enabled)
    return out


def get_tools_for_runtime(*, data_dir: Path | None = None) -> list[dict[str, Any]]:
    """
    Возвращает активные tools для runtime.
    Если data_dir не передан или overrides недоступен — используем OPENAI_TOOLS_DEFAULT.
    """
    if data_dir is None:
        return list(OPENAI_TOOLS_DEFAULT)
    enabled_map = _load_enabled_from_overrides(data_dir)
    if not enabled_map:
        return list(OPENAI_TOOLS_DEFAULT)
    out: list[dict[str, Any]] = []
    for schema in OPENAI_TOOLS_CATALOG:
        name = _tool_name(schema)
        if not name:
            continue
        if enabled_map.get(name, True):
            out.append(schema)
    return out
