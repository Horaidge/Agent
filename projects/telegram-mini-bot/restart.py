"""Перезапуск процесса бота после смены override (подтягивает промпт с диска)."""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def spawn_bot_restart(project_root: Path) -> None:
    script = project_root / "scripts" / "restart_bot.sh"
    if not script.is_file():
        logger.error("Нет scripts/restart_bot.sh — перезапуск вручную")
        return
    subprocess.Popen(
        ["bash", str(script)],
        cwd=str(project_root),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Запланирован перезапуск бота через %s", script)
    sys.exit(0)
