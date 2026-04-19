"""
Инструменты модели и реализации: одна точка входа.

- JSON-схемы для OpenAI: `openai_definitions.py`
- Реализации (Qwen, Wan и т.д.): `image_tools.py`, `video_tools.py`
- Модели-ориентированные tool-модули: `model_tools/*`
"""

from services.tools.image_tools import (
    tool_edit_image,
    tool_generate_base_character,
    tool_generate_image,
)
from services.tools.openai_definitions import (
    DREAM_PIPELINE_TOOL,
    GENERATE_IMAGE_TOOL,
    OPENAI_TOOLS_CATALOG,
    OPENAI_TOOLS_DEFAULT,
)

__all__ = [
    "DREAM_PIPELINE_TOOL",
    "GENERATE_IMAGE_TOOL",
    "OPENAI_TOOLS_CATALOG",
    "OPENAI_TOOLS_DEFAULT",
    "tool_edit_image",
    "tool_generate_base_character",
    "tool_generate_image",
]
