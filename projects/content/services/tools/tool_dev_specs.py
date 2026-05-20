"""
Метаданные для Dev UI: реальная структура инструментов из кода (схема, дефолты, цепочка вызова).

Источники: model_tools/*, services/tools/image_tools.py, video_tools.py.
"""
from __future__ import annotations

import inspect
import json
from dataclasses import asdict
from typing import Any

from services.tools.model_tools.dream_pipeline_tool import (
    OPENAI_TOOL_SCHEMA as DREAM_SCHEMA,
    PIPELINE_INTERNAL_STAGES,
    TOOL_DESCRIPTION as DREAM_DESC,
    TOOL_NAME as DREAM_NAME,
    parse_dream_pipeline_args,
)
from services.tools.model_tools.generate_image_tool import (
    OPENAI_TOOL_SCHEMA as GEN_IMG_SCHEMA,
    TOOL_DESCRIPTION as GEN_IMG_DESC,
    TOOL_NAME as GEN_IMG_NAME,
    parse_generate_image_args,
)
from services.tools.model_tools.generate_image_openrouter_tool import (
    OPENAI_TOOL_SCHEMA as OR_IMG_SCHEMA,
    TOOL_DESCRIPTION as OR_IMG_DESC,
    TOOL_NAME as OR_IMG_NAME,
    parse_generate_image_openrouter_args,
)
from services.tools.model_tools.image_to_video_tool import (
    OPENAI_TOOL_SCHEMA as I2V_SCHEMA,
    TOOL_DESCRIPTION as I2V_DESC,
    TOOL_NAME as I2V_NAME,
)
from services.tools.model_tools.video_trim_start_tool import (
    OPENAI_TOOL_SCHEMA as TRIM_SCHEMA,
    TOOL_DESCRIPTION as TRIM_DESC,
    TOOL_NAME as TRIM_NAME,
)
from services.tools.model_tools.last_frame_reference_tool import (
    OPENAI_TOOL_SCHEMA as LAST_FRAME_SCHEMA,
    TOOL_DESCRIPTION as LAST_FRAME_DESC,
    TOOL_NAME as LAST_FRAME_NAME,
)
from services.tools.model_tools.concat_video_clips_tool import (
    OPENAI_TOOL_SCHEMA as CONCAT_SCHEMA,
    TOOL_DESCRIPTION as CONCAT_DESC,
    TOOL_NAME as CONCAT_NAME,
)
from services.tools.video_tools import tool_concat_remote_video_urls, tool_image_to_video


def _build_call_contract(schema: dict[str, Any]) -> dict[str, Any]:
    fn = schema.get("function") or {}
    fn_name = str(fn.get("name") or "").strip()
    params = fn.get("parameters") or {}
    props: dict[str, Any] = params.get("properties") or {}
    required = [str(x) for x in (params.get("required") or []) if str(x).strip()]

    example_args: dict[str, Any] = {}
    for pname, spec in props.items():
        if not isinstance(spec, dict):
            continue
        ptype = spec.get("type")
        enum_vals = spec.get("enum") if isinstance(spec.get("enum"), list) else None
        if enum_vals:
            example_args[pname] = enum_vals[0]
            continue
        if ptype == "string":
            example_args[pname] = f"<{pname}>"
        elif ptype == "integer":
            mn = spec.get("minimum")
            example_args[pname] = int(mn) if isinstance(mn, (int, float)) else 1
        elif ptype == "number":
            mn = spec.get("minimum")
            example_args[pname] = float(mn) if isinstance(mn, (int, float)) else 1.0
        elif ptype == "boolean":
            example_args[pname] = True
        elif ptype == "array":
            example_args[pname] = []
        elif ptype == "object":
            example_args[pname] = {}
        else:
            example_args[pname] = f"<{pname}>"

    # В OpenAI function calling аргументы передаются JSON-строкой.
    args_min = {k: example_args[k] for k in required if k in example_args}
    if not args_min and example_args:
        first_key = next(iter(example_args))
        args_min[first_key] = example_args[first_key]

    payload = {
        "type": "function",
        "function": {
            "name": fn_name,
            "arguments": json.dumps(args_min, ensure_ascii=False),
        },
    }
    args_min_json = json.dumps(args_min, ensure_ascii=False, indent=2)
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

    if required:
        req_str = ", ".join(f"`{x}`" for x in required)
        rule = (
            f"Вызывать `{fn_name}` только когда пользовательский запрос явно соответствует задаче инструмента. "
            f"Передавать валидный JSON в `arguments` и обязательно заполнить: {req_str}."
        )
    else:
        rule = (
            f"Вызывать `{fn_name}` только при релевантном намерении пользователя. "
            "В `arguments` передавать валидный JSON по схеме инструмента."
        )

    return {
        "required_fields": required,
        "invocation_rule": rule,
        "arguments_min_json": args_min_json,
        "call_payload_json": payload_json,
    }


def _openai_param_rows(schema: dict[str, Any]) -> dict[str, Any]:
    fn = schema.get("function") or {}
    params = fn.get("parameters") or {}
    props: dict[str, Any] = params.get("properties") or {}
    required = set(params.get("required") or [])
    rows: list[dict[str, Any]] = []
    for pname, spec in props.items():
        if not isinstance(spec, dict):
            continue
        rows.append(
            {
                "name": pname,
                "type": spec.get("type"),
                "description": (spec.get("description") or "").strip(),
                "enum": spec.get("enum"),
                "minimum": spec.get("minimum"),
                "maximum": spec.get("maximum"),
                "required": pname in required,
            }
        )
    return {"function_description": (fn.get("description") or "").strip(), "parameters": rows}


def _spec_generate_image_openrouter() -> dict[str, Any]:
    try:
        args = parse_generate_image_openrouter_args({"prompt": "."})
        py_defaults = {k: v for k, v in asdict(args).items()}
    except Exception:  # noqa: BLE001
        py_defaults = {"prompt": "", "aspect_ratio": None, "image_size": None, "model": None}
    return {
        "name": OR_IMG_NAME,
        "module_summary": OR_IMG_DESC,
        "openai": _openai_param_rows(OR_IMG_SCHEMA),
        "call_contract": _build_call_contract(OR_IMG_SCHEMA),
        "python_defaults": py_defaults,
        "pipeline": [
            "parse_generate_image_openrouter_args → tool_generate_image_openrouter.",
            "services/images/openrouter_image_client.py: POST {base}/chat/completions, modalities [image, text].",
            "Ключ: OPENROUTER_API_KEY (только окружение / Settings).",
        ],
        "notes": [
            "Модель по умолчанию: OPENROUTER_IMAGE_MODEL (например google/gemini-2.5-flash-image).",
            "Ответ: message.images[].image_url.url (часто data URI base64).",
        ],
    }


def _spec_generate_image() -> dict[str, Any]:
    args = parse_generate_image_args({"prompt": "."})
    py_defaults = {k: v for k, v in asdict(args).items()}
    return {
        "name": GEN_IMG_NAME,
        "module_summary": GEN_IMG_DESC,
        "openai": _openai_param_rows(GEN_IMG_SCHEMA),
        "call_contract": _build_call_contract(GEN_IMG_SCHEMA),
        "python_defaults": py_defaults,
        "pipeline": [
            "Аргументы из чата: JSON → parse_generate_image_args (нормализация, clamp n∈[1,6]).",
            "execute_generate_image → tool_generate_image (services/tools/image_tools.py).",
            "generate_image_from_prompt — Qwen Image через DashScope (размер и model пробрасываются как есть).",
        ],
        "notes": [
            "Режимы разрешения — фиксированный enum в схеме (строки вида 1024*1536).",
            "Поле model — строка; в UI Generation tab используются qwen-image-2.0 и qwen-image-2.0-pro.",
        ],
    }


def _spec_image_to_video() -> dict[str, Any]:
    sig = inspect.signature(tool_image_to_video)
    py_defaults: dict[str, Any] = {}
    for pname, p in sig.parameters.items():
        if pname in ("job_extra",) or p.kind == inspect.Parameter.VAR_KEYWORD:
            continue
        if p.default is not inspect.Parameter.empty:
            py_defaults[pname] = p.default
    return {
        "name": I2V_NAME,
        "module_summary": I2V_DESC,
        "openai": _openai_param_rows(I2V_SCHEMA),
        "call_contract": _build_call_contract(I2V_SCHEMA),
        "python_defaults": py_defaults,
        "pipeline": [
            "Аргументы из модели по OPENAI_TOOL_SCHEMA; в Telegram-боте — tool_image_to_video (async job).",
            "VideoJobService.create_video_job → Mongo video_jobs, фоновый polling Wan.",
            "wan2.7-i2v: first_frame = image_url; необязательный last_frame_url → input.media last_frame.",
            "Параметры duration/resolution валидируются бэкендом; model по умолчанию wan2.7-i2v (см. video_tools).",
        ],
        "notes": [
            "Инструмент async: ответ обычно содержит job_id, не готовое видео.",
            "resolution в схеме: 480p / 720p / 1080p; дефолт в Python чаще 720p.",
        ],
    }


def _spec_dream_pipeline() -> dict[str, Any]:
    try:
        args = parse_dream_pipeline_args({"dream_text": "."})
        py_defaults = asdict(args)
    except Exception:  # noqa: BLE001
        py_defaults = {"dream_text": "", "telegram_user_id": None}
    return {
        "name": DREAM_NAME,
        "module_summary": DREAM_DESC,
        "openai": _openai_param_rows(DREAM_SCHEMA),
        "call_contract": _build_call_contract(DREAM_SCHEMA),
        "python_defaults": py_defaults,
        "internal_stages": list(PIPELINE_INTERNAL_STAGES),
        "pipeline": [
            "Фасад generate_dream_pipeline: один tool-call запускает многошаговый сценарий.",
            "Внутри: декомпозиция сна → кадры (в т.ч. generate_image) → анимация → финальная сборка видео.",
        ],
        "notes": [
            "Интерфейс инструмента упрощён: передаётся только dream_text и telegram_user_id.",
        ],
    }


def _spec_video_trim_start() -> dict[str, Any]:
    return {
        "name": TRIM_NAME,
        "module_summary": TRIM_DESC,
        "openai": _openai_param_rows(TRIM_SCHEMA),
        "call_contract": _build_call_contract(TRIM_SCHEMA),
        "python_defaults": {"trim_start_sec": 0.5},
        "pipeline": [
            "Вход: video_url + trim_start_sec.",
            "Назначение: убрать стартовый разгон/инерцию в начале клипа.",
            "Обычно применяется после image_to_video перед финальной сборкой.",
        ],
        "notes": [
            "Рекомендуемый диапазон для Dream Director: 0.3..1.0 сек.",
        ],
    }


def _spec_last_frame_reference() -> dict[str, Any]:
    return {
        "name": LAST_FRAME_NAME,
        "module_summary": LAST_FRAME_DESC,
        "openai": _openai_param_rows(LAST_FRAME_SCHEMA),
        "call_contract": _build_call_contract(LAST_FRAME_SCHEMA),
        "python_defaults": {"scene_index": 1},
        "pipeline": [
            "Вход: video_url текущей/предыдущей сцены.",
            "Извлекается последний кадр и используется как reference image для continuity.",
            "Обычно вызывается при overlap=true для продолжения сцены.",
        ],
        "notes": [
            "Полезно для стабильности персонажа/кадра между соседними шотами.",
        ],
    }


def _spec_concat_video_clips() -> dict[str, Any]:
    return {
        "name": CONCAT_NAME,
        "module_summary": CONCAT_DESC,
        "openai": _openai_param_rows(CONCAT_SCHEMA),
        "call_contract": _build_call_contract(CONCAT_SCHEMA),
        "python_defaults": {"video_urls": [], "label": None},
        "pipeline": [
            "ChatOrchestrator → tool_concat_remote_video_urls (services/tools/video_tools.py).",
            "assemble_remote_mp4s: скачать каждый URL → ffmpeg concat demuxer → ui/dev/static/chat_concat/.",
        ],
        "notes": [
            "Нужны прямые http(s) ссылки на уже готовые mp4.",
            "Публичный путь ответа: /dev/static/chat_concat/<file>.mp4 (при mount dev static).",
        ],
    }


_SPECS: dict[str, dict[str, Any]] = {
    GEN_IMG_NAME: _spec_generate_image(),
    OR_IMG_NAME: _spec_generate_image_openrouter(),
    I2V_NAME: _spec_image_to_video(),
    CONCAT_NAME: _spec_concat_video_clips(),
    DREAM_NAME: _spec_dream_pipeline(),
    TRIM_NAME: _spec_video_trim_start(),
    LAST_FRAME_NAME: _spec_last_frame_reference(),
}


def get_tool_dev_spec(tool_name: str) -> dict[str, Any] | None:
    """Возвращает структурированное описание инструмента для Dev UI или None."""
    key = (tool_name or "").strip()
    if not key:
        return None
    return _SPECS.get(key)
