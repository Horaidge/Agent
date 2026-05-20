"""
Песочница Сборщика: один раунд OpenAI chat + tools, исполнение tools, финальный ответ без tools.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from services.llm.openai_chat_service import OpenAIChatService
from services.tools.openrouter_image_tools import tool_generate_image_openrouter
from services.tools.openai_definitions import OPENAI_TOOLS_CATALOG
from services.tools.video_tools import tool_image_to_video

logger = logging.getLogger(__name__)

_ASSEMBLER_DEFAULT_TOOLS = [
    "generate_image_openrouter",
    "image_to_video",
    "video_trim_start",
    "last_frame_as_reference",
]


def _schemas_for_tools(names: list[str]) -> list[dict[str, Any]]:
    want = {n.strip() for n in names if n and str(n).strip()}
    out: list[dict[str, Any]] = []
    for schema in OPENAI_TOOLS_CATALOG:
        fn = (schema.get("function") or {}).get("name")
        if not fn or fn not in want:
            continue
        out.append(schema)
    return out


def _tool_message_for_model(payload: dict[str, Any]) -> str:
    """Сжимает огромные data URL в summary для следующего раунда LLM (картинки уже в artifacts)."""
    try:
        s = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        s = str(payload)
    if len(s) <= 12000:
        return s
    return s[:8000] + "\n… [truncated for model context; см. артефакты в UI]"


def _execute_tool(name: str, args_raw: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    artifacts: list[dict[str, Any]] = []
    try:
        args = json.loads(args_raw or "{}")
        if not isinstance(args, dict):
            args = {}
    except Exception:
        args = {}

    if name == "generate_image_openrouter":
        ref_raw = args.get("reference_image_urls")
        ref_list: list[str] | None = None
        if isinstance(ref_raw, list):
            ref_list = [str(x).strip() for x in ref_raw if str(x).strip()]
            if not ref_list:
                ref_list = None
        elif isinstance(ref_raw, str) and ref_raw.strip():
            ref_list = [ref_raw.strip()]
        result = tool_generate_image_openrouter(
            str(args.get("prompt") or "").strip(),
            aspect_ratio=str(args["aspect_ratio"]).strip()
            if args.get("aspect_ratio")
            else None,
            image_size=str(args["image_size"]).strip()
            if args.get("image_size")
            else None,
            model=str(args["model"]).strip() if args.get("model") else None,
            reference_image_urls=ref_list,
        )
        d = result.to_dict()
        urls = list(result.image_urls or [])
        if urls:
            artifacts.append(
                {
                    "kind": "image",
                    "tool": name,
                    "urls": urls,
                }
            )
        return d, artifacts

    if name == "image_to_video":
        out = tool_image_to_video(
            prompt=str(args.get("prompt") or "").strip(),
            image_url=str(args.get("image_url") or "").strip(),
            model=str(args.get("model") or "wan2.7-i2v"),
            duration=int(args.get("duration") or 4),
            resolution=str(args.get("resolution") or "720p"),
            owner_user_id=str(args.get("owner_user_id") or "assembler_sandbox"),
            last_frame_url=str(args["last_frame_url"]).strip()
            if args.get("last_frame_url")
            else None,
        )
        vu = out.get("video_url")
        if vu:
            artifacts.append(
                {
                    "kind": "video",
                    "tool": name,
                    "video_url": vu,
                    "job_id": out.get("job_id"),
                }
            )
        elif out.get("job_id"):
            artifacts.append(
                {
                    "kind": "video_pending",
                    "tool": name,
                    "job_id": out.get("job_id"),
                    "status": out.get("status"),
                }
            )
        return out, artifacts

    if name == "video_trim_start":
        return (
            {
                "ok": False,
                "error": "В dev-песочнице video_trim_start пока не исполняется (нет локального ffmpeg-контура).",
            },
            [],
        )

    if name == "last_frame_as_reference":
        return (
            {
                "ok": False,
                "error": "В dev-песочнице last_frame_as_reference пока не исполняется (извлечение кадра).",
            },
            [],
        )

    return {"ok": False, "error": f"unknown_tool: {name}"}, []


def _assistant_message_dict(msg: Any) -> dict[str, Any]:
    """Собирает сообщение assistant для повторного chat (после tool)."""
    role = getattr(msg, "role", None) or "assistant"
    content = getattr(msg, "content", None)
    out: dict[str, Any] = {"role": role, "content": content}
    tool_calls = getattr(msg, "tool_calls", None)
    if not tool_calls:
        return out
    serialized: list[dict[str, Any]] = []
    for tc in tool_calls:
        fn = getattr(tc, "function", None)
        serialized.append(
            {
                "id": getattr(tc, "id", "") or "",
                "type": getattr(tc, "type", None) or "function",
                "function": {
                    "name": getattr(fn, "name", "") if fn else "",
                    "arguments": getattr(fn, "arguments", "") if fn else "",
                },
            }
        )
    out["tool_calls"] = serialized
    return out


async def run_assembler_sandbox(
    openai: OpenAIChatService,
    *,
    director_obj: dict[str, Any],
    system_prompt: str,
    human_logic: str,
    enabled_tool_names: list[str] | None,
) -> dict[str, Any]:
    names = enabled_tool_names if enabled_tool_names else list(_ASSEMBLER_DEFAULT_TOOLS)
    tools = _schemas_for_tools(names)
    if not tools:
        return {
            "ok": False,
            "error": "Не выбрано ни одного известного инструмента (generate_image_openrouter, image_to_video, …).",
            "artifacts": [],
            "tool_steps": [],
            "assistant_final": "",
            "had_tool_calls": False,
        }

    user_text = (
        "Ниже JSON от Режиссёра (исполняй по плану сцен, вызывай инструменты по необходимости).\n"
        f"{json.dumps(director_obj, ensure_ascii=False, indent=2)}\n\n"
        "Инструкции оператора (логика исполнения):\n"
        f"{(human_logic or '').strip() or '(нет дополнительных инструкций)'}"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": (system_prompt or "").strip()},
        {"role": "user", "content": user_text},
    ]

    tool_steps: list[dict[str, Any]] = []
    all_artifacts: list[dict[str, Any]] = []

    try:
        resp = await openai.chat_completion(messages, tools=tools)
    except Exception as e:  # noqa: BLE001
        logger.exception("assembler_sandbox: chat_completion failed")
        return {
            "ok": False,
            "error": str(e),
            "artifacts": [],
            "tool_steps": [],
            "assistant_final": "",
            "had_tool_calls": False,
        }

    choice = resp.choices[0]
    msg = choice.message
    messages.append(_assistant_message_dict(msg))

    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        fn = getattr(tc, "function", None)
        tname = getattr(fn, "name", "") if fn else ""
        args_raw = getattr(fn, "arguments", "") if fn else "{}"
        tid = getattr(tc, "id", "") or ""
        payload, arts = _execute_tool(tname, str(args_raw))
        all_artifacts.extend(arts)
        tool_steps.append(
            {
                "name": tname,
                "ok": bool(payload.get("ok", True)) if isinstance(payload, dict) else True,
                "result_summary": _tool_message_for_model(payload)
                if isinstance(payload, dict)
                else str(payload)[:2000],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tid,
                "content": _tool_message_for_model(payload)
                if isinstance(payload, dict)
                else str(payload),
            }
        )

    assistant_final = ""
    if tool_calls:
        try:
            resp2 = await openai.chat_completion(messages, tools=None)
            assistant_final = (
                resp2.choices[0].message.content
                or getattr(resp2.choices[0].message, "content", "")
                or ""
            )
        except Exception as e:  # noqa: BLE001
            assistant_final = f"(Не удалось получить финальный ответ модели: {e})"
    else:
        assistant_final = str(msg.content or "")

    return {
        "ok": True,
        "error": "",
        "artifacts": all_artifacts,
        "tool_steps": tool_steps,
        "assistant_final": assistant_final,
        "had_tool_calls": bool(tool_calls),
    }

