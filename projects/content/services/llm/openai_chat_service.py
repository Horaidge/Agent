"""Вызовы OpenAI Chat Completions с опциональным tool calling."""
from __future__ import annotations

import logging
from typing import Any

import httpx
from openai import AsyncOpenAI

from services.llm.system_prompt_loader import merge_with_global_model_policy, load_global_model_policy
from services.tools.openai_definitions import GENERATE_IMAGE_TOOL

logger = logging.getLogger(__name__)

class OpenAIChatService:
    """Обёртка над AsyncOpenAI; ключ и модель из настроек."""

    def __init__(self, api_key: str | None, model: str, proxy_url: str | None = None) -> None:
        self._model = model
        self._client: AsyncOpenAI | None
        if api_key and api_key.strip():
            proxy = (proxy_url or "").strip()
            if proxy:
                self._client = AsyncOpenAI(
                    api_key=api_key.strip(),
                    http_client=httpx.AsyncClient(proxy=proxy),
                )
            else:
                self._client = AsyncOpenAI(api_key=api_key.strip())
        else:
            self._client = None

    @property
    def configured(self) -> bool:
        return self._client is not None

    @staticmethod
    def _messages_with_global_policy(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Дополняет первый system-сообщением из `global_model_policy.md` (если файл непустой)."""
        if not load_global_model_policy():
            return messages
        out: list[dict[str, Any]] = []
        merged = False
        for m in messages:
            if not merged and m.get("role") == "system":
                raw = m.get("content")
                base = raw if isinstance(raw, str) else ""
                out.append({**m, "content": merge_with_global_model_policy(base)})
                merged = True
            else:
                out.append(dict(m))
        if not merged:
            out.insert(0, {"role": "system", "content": merge_with_global_model_policy("")})
        return out

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY не задан (проверьте env / Settings)")
        messages = self._messages_with_global_policy(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        logger.info(
            "OpenAI chat.completions: model=%s messages=%s tools=%s",
            self._model,
            len(messages),
            bool(tools),
        )
        return await self._client.chat.completions.create(**kwargs)

    async def json_completion(
        self,
        *,
        system: str,
        user: str,
    ) -> str:
        """Один раунд Chat Completions с response_format=json_object (без tools)."""
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY не задан (проверьте env / Settings)")
        merged_system = merge_with_global_model_policy(system)
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": merged_system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        msg = resp.choices[0].message
        return (msg.content or "").strip()
