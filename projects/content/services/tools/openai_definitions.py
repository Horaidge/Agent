"""
Реестр инструментов для OpenAI Chat Completions (function calling).

Источник истины по каждому инструменту лежит в `services/tools/model_tools/*`:
- schema (что видит модель),
- описание,
- правила аргументов.
"""
from __future__ import annotations

from typing import Any

from services.tools.model_tools.generate_image_tool import (
    OPENAI_TOOL_SCHEMA as GENERATE_IMAGE_TOOL,
)
from services.tools.model_tools.dream_pipeline_tool import (
    OPENAI_TOOL_SCHEMA as DREAM_PIPELINE_TOOL,
)
from services.tools.model_tools.image_to_video_tool import (
    OPENAI_TOOL_SCHEMA as IMAGE_TO_VIDEO_TOOL,
)

# Список tools, передаваемых в chat по умолчанию (расширяйте по мере добавления схем выше)
OPENAI_TOOLS_DEFAULT: list[dict[str, Any]] = [
    GENERATE_IMAGE_TOOL,
]

# Полный каталог доступных описаний (включая неактивные по умолчанию)
OPENAI_TOOLS_CATALOG: list[dict[str, Any]] = [
    GENERATE_IMAGE_TOOL,
    DREAM_PIPELINE_TOOL,
    IMAGE_TO_VIDEO_TOOL,
]
