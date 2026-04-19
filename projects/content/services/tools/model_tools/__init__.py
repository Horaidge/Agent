"""Каталог model-facing tools: схемы, описания и парсеры аргументов."""

from services.tools.model_tools.generate_image_tool import (
    OPENAI_TOOL_SCHEMA as GENERATE_IMAGE_TOOL_SCHEMA,
)
from services.tools.model_tools.dream_pipeline_tool import (
    OPENAI_TOOL_SCHEMA as DREAM_PIPELINE_TOOL_SCHEMA,
)
from services.tools.model_tools.image_to_video_tool import (
    OPENAI_TOOL_SCHEMA as IMAGE_TO_VIDEO_TOOL_SCHEMA,
)

__all__ = [
    "DREAM_PIPELINE_TOOL_SCHEMA",
    "GENERATE_IMAGE_TOOL_SCHEMA",
    "IMAGE_TO_VIDEO_TOOL_SCHEMA",
]

