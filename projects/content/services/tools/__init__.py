"""
Инструменты модели и реализации: одна точка входа.

- JSON-схемы для OpenAI: `openai_definitions.py`
- Реализации (Qwen, Wan и т.д.): `image_tools.py`, `video_tools.py`
"""

from services.tools.image_tools import (
    tool_edit_image,
    tool_generate_base_character,
    tool_generate_image,
)
from services.tools.openai_definitions import GENERATE_IMAGE_TOOL, OPENAI_TOOLS_DEFAULT

__all__ = [
    "GENERATE_IMAGE_TOOL",
    "OPENAI_TOOLS_DEFAULT",
    "tool_edit_image",
    "tool_generate_base_character",
    "tool_generate_image",
]
