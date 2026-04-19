"""Контекст запроса: trace_id для связки webhook → handlers → Mongo → события."""
from __future__ import annotations

import contextvars

current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_trace_id",
    default=None,
)
