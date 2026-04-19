"""Рекурсивное удаление чувствительных полей из dict/list перед записью в observability."""
from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(token|secret|password|api_key|apikey|authorization|bearer|credential)",
    re.I,
)


def sanitize_for_debug(obj: Any, *, depth: int = 0) -> Any:
    if depth > 24:
        return "<max depth>"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return _sanitize_string(obj)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            ks = str(k)
            if _SENSITIVE_KEY.search(ks):
                out[ks] = "***"
            else:
                out[ks] = sanitize_for_debug(v, depth=depth + 1)
        return out
    if isinstance(obj, list):
        return [sanitize_for_debug(x, depth=depth + 1) for x in obj[:500]]
    if isinstance(obj, tuple):
        return [sanitize_for_debug(x, depth=depth + 1) for x in obj[:500]]
    return str(obj)[:2000]


def _sanitize_string(s: str) -> str:
    t = s.strip()
    if t.startswith("sk-") and len(t) > 20:
        return "sk-***"
    if t.startswith("Bearer ") and len(t) > 12:
        return "Bearer ***"
    if len(s) > 100_000:
        return s[:50_000] + "\n... [truncated]"
    return s
