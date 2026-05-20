"""RAG: эмбеддинг запроса + match_telegram_rag_chunks в Supabase."""
from __future__ import annotations

import logging
from typing import Any

import httpx
from openai import OpenAI

from config import Settings

logger = logging.getLogger(__name__)

# Ограничение размера блока контекста в символах (~ похоже на бюджет токенов)
RAG_CONTEXT_MAX_CHARS = 22000
RAG_CHUNK_MAX_CHARS = 3500


def _to_pg_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def _format_chunks(rows: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    total = 0
    for i, row in enumerate(rows, 1):
        content = (row.get("content") or "").strip()
        if len(content) > RAG_CHUNK_MAX_CHARS:
            content = content[: RAG_CHUNK_MAX_CHARS - 1] + "…"
        sim = row.get("similarity")
        sim_s = f"{float(sim):.3f}" if sim is not None else "?"
        line = f"[{i}] (релевантность {sim_s})\n{content}"
        if total + len(line) + 2 > RAG_CONTEXT_MAX_CHARS:
            break
        parts.append(line)
        total += len(line) + 2
    return "\n\n".join(parts)


class RagRetriever:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._supabase = None
        http_client: httpx.Client | None = None
        proxy = (settings.openai_proxy_url or "").strip()
        if proxy:
            http_client = httpx.Client(proxy=proxy, timeout=120.0)
        self._openai = OpenAI(api_key=settings.openai_api_key, http_client=http_client)

    def _client(self):
        if self._supabase is None:
            from supabase import create_client

            self._supabase = create_client(
                self._settings.supabase_url,
                self._settings.supabase_service_role_key,
            )
        return self._supabase

    def build_context(self, user_text: str) -> str:
        if not self._settings.rag_enabled():
            return ""
        text = (user_text or "").strip()
        if len(text) < 4:
            return ""
        try:
            emb_res = self._openai.embeddings.create(
                model=self._settings.openai_embedding_model,
                input=[text],
            )
            vec = emb_res.data[0].embedding
            if len(vec) != 1536:
                logger.warning("RAG: неожиданная размерность эмбеддинга %s", len(vec))
                return ""
            lit = _to_pg_vector_literal(vec)
            res = (
                self._client()
                .rpc(
                    "match_telegram_rag_chunks",
                    {"query_embedding": lit, "match_count": self._settings.rag_top_k},
                )
                .execute()
            )
            rows = res.data or []
            if not rows:
                return ""
            return _format_chunks(rows)
        except Exception:
            logger.exception("RAG: ошибка поиска, отвечаем без контекста")
            return ""
