"""Запись событий расхода в dev_usage_ledger (Mongo)."""
from __future__ import annotations

import logging
from typing import Any

from storage.dev_usage_ledger_repository import DevUsageLedgerRepository

logger = logging.getLogger(__name__)


def normalize_openrouter_usage(raw: Any) -> tuple[int | None, int | None, int | None, float | None]:
    """Возвращает (input_tokens, output_tokens, total_tokens, cost_usd) из объекта usage OpenRouter."""
    if not isinstance(raw, dict):
        return None, None, None, None
    inp = raw.get("prompt_tokens")
    if inp is None:
        inp = raw.get("input_tokens")
    out = raw.get("completion_tokens")
    if out is None:
        out = raw.get("output_tokens")
    tot = raw.get("total_tokens")
    cost = raw.get("total_cost") or raw.get("cost") or raw.get("generation_cost")
    try:
        cost_f = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_f = None
    try:
        i = int(inp) if inp is not None else None
    except (TypeError, ValueError):
        i = None
    try:
        o = int(out) if out is not None else None
    except (TypeError, ValueError):
        o = None
    try:
        t = int(tot) if tot is not None else None
    except (TypeError, ValueError):
        t = None
    return i, o, t, cost_f


def record_dev_usage(
    repo: DevUsageLedgerRepository | None,
    *,
    category: str,
    provider: str,
    model: str | None,
    source: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_usd: float | None = None,
    meta: dict[str, Any] | None = None,
    ok: bool = True,
) -> None:
    if repo is None:
        return
    try:
        repo.insert_event_sync(
            {
                "category": category,
                "provider": provider,
                "model": model,
                "source": source,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "meta": meta or {},
                "ok": ok,
            }
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("dev_usage_ledger: не удалось записать событие: %s", e)
