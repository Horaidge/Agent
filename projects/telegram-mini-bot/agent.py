"""Асинхронный агент: OpenAI + tools + режимы (без эвристик по тексту)."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from aiogram.types import Message
from openai import OpenAI

from audit_log import append_turn
from config import Settings
from dream_runtime import run_dream_video_pipeline
from modes import BotMode
from prompt_store import PromptStore
from rag import RagRetriever
from tools import build_openai_tools

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6


@dataclass
class AgentReply:
    text: str
    prompt_updated: bool = False
    needs_restart: bool = False
    dream_pipeline_started: bool = False


def _compact_history_for_audit(hist: list[dict[str, str]]) -> str:
    chunks: list[str] = []
    for m in hist[-14:]:
        role = str(m.get("role", ""))
        body = str(m.get("content", ""))
        if len(body) > 1200:
            body = body[:1197] + "…"
        chunks.append(f"[{role}]\n{body}")
    return "\n\n— — —\n\n".join(chunks)


class ChatAgent:
    def __init__(
        self,
        settings: Settings,
        store: PromptStore,
        *,
        dream_pipeline_available: bool,
    ) -> None:
        self._settings = settings
        self._store = store
        self._rag = RagRetriever(settings)
        self._dream_available = dream_pipeline_available
        self._tools = build_openai_tools(dream_pipeline_available=dream_pipeline_available)
        http_client: httpx.Client | None = None
        proxy = (settings.openai_proxy_url or "").strip()
        if proxy:
            http_client = httpx.Client(proxy=proxy, timeout=120.0)
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            http_client=http_client,
        )

    async def reply_async(
        self,
        message: Message,
        chat_id: int,
        user_text: str,
        mode: BotMode,
    ) -> AgentReply:
        base = self._store.read_base_prompt()
        override = self._store.read_override_prompt()
        full_system = self._store.compose_system_prompt(
            mode,
            dream_pipeline_available=self._dream_available,
        )
        prior = self._store.load_history(chat_id)
        hist_summary = _compact_history_for_audit(prior)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": full_system},
            *prior,
            {"role": "user", "content": user_text},
        ]

        prompt_updated = False
        needs_restart = False
        dream_started = False
        rag_used = ""

        for _ in range(MAX_TOOL_ROUNDS):
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._settings.openai_model,
                messages=messages,
                tools=self._tools,
                tool_choice="auto",
            )
            choice = response.choices[0].message
            tool_calls = choice.tool_calls or []
            if not tool_calls:
                text = (choice.content or "").strip() or "…"
                self._persist_turn(
                    chat_id=chat_id,
                    user_text=user_text,
                    assistant_text=text,
                    base_prompt=base,
                    override_prompt=override,
                    full_system=full_system,
                    rag_context=rag_used,
                    history_summary=hist_summary,
                    mode=mode,
                )
                self._store.append_history(chat_id, "user", user_text)
                self._store.append_history(chat_id, "assistant", text)
                return AgentReply(
                    text=text,
                    prompt_updated=prompt_updated,
                    needs_restart=needs_restart,
                    dream_pipeline_started=dream_started,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_result, flags = await self._execute_tool(
                    message=message,
                    name=name,
                    args=args,
                )
                if flags.get("prompt_updated"):
                    prompt_updated = True
                if flags.get("needs_restart"):
                    needs_restart = True
                if flags.get("dream_started"):
                    dream_started = True
                if name == "search_public_knowledge" and tool_result:
                    rag_used = (rag_used + "\n" + tool_result).strip()

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    }
                )

        return AgentReply(
            text="Не удалось завершить цикл инструментов. Попробуйте ещё раз.",
            prompt_updated=prompt_updated,
            needs_restart=needs_restart,
            dream_pipeline_started=dream_started,
        )

    async def _execute_tool(
        self,
        *,
        message: Message,
        name: str,
        args: dict[str, Any],
    ) -> tuple[str, dict[str, bool]]:
        flags: dict[str, bool] = {}
        if name == "update_system_prompt_override":
            new_override = str(args.get("new_override", "")).strip()
            if new_override:
                self._store.update_system_prompt(new_override)
                flags["prompt_updated"] = True
                flags["needs_restart"] = True
                return (
                    "Override сохранён в data/system_override.txt. "
                    "Бот перезапустится, чтобы подтянуть промпт.",
                    flags,
                )
            return "Ошибка: пустой new_override.", flags

        if name == "search_public_knowledge":
            query = str(args.get("query", "")).strip()
            if not query:
                return "Ошибка: пустой query.", flags
            ctx = await asyncio.to_thread(self._rag.build_context, query)
            if not ctx:
                return "По запросу релевантных фрагментов в публичной базе не найдено.", flags
            return f"Фрагменты публичной базы:\n\n{ctx}", flags

        if name == "search_internal_documents":
            return (
                "Внутренняя база и отдельный RAG для файлов организации — в разработке. "
                "Пока используй search_public_knowledge или ответь из контекста честно.",
                flags,
            )

        if name == "generate_dream_video":
            dream_text = str(args.get("dream_text", "")).strip()
            result = await run_dream_video_pipeline(message, dream_text)
            if "запущен" in result.lower() or "run_id=" in result.lower():
                flags["dream_started"] = True
            return result, flags

        return f"Неизвестный инструмент: {name}", flags

    def _persist_turn(
        self,
        *,
        chat_id: int,
        user_text: str,
        assistant_text: str,
        base_prompt: str,
        override_prompt: str,
        full_system: str,
        rag_context: str,
        history_summary: str,
        mode: BotMode,
    ) -> None:
        try:
            append_turn(
                self._settings.data_dir,
                chat_id=chat_id,
                user_text=user_text,
                assistant_text=assistant_text,
                rag_context=rag_context,
                system_prompt=base_prompt,
                override_prompt=override_prompt,
                mode=mode.value,
                full_system_message=full_system,
                history_summary=history_summary,
                model=self._settings.openai_model,
            )
        except Exception:
            logger.exception("Не удалось записать audit_log")
