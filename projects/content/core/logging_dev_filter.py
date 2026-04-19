"""Подавление шума access-log: успешные GET к /dev/ (HTMX polling в dev-консоли)."""
from __future__ import annotations

import logging


class SuppressDevUiSuccessfulAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "GET " not in msg or "/dev/" not in msg:
            return True
        if " 200" in msg:
            if any(x in msg for x in (" 500", " 502", " 503", " 429")):
                return True
            return False
        return True


def install_dev_access_log_filter() -> None:
    """Вызывать из main.py и при старте приложения (uvicorn может пересоздать логгеры)."""
    log = logging.getLogger("uvicorn.access")
    if any(isinstance(f, SuppressDevUiSuccessfulAccessFilter) for f in log.filters):
        return
    log.addFilter(SuppressDevUiSuccessfulAccessFilter())
