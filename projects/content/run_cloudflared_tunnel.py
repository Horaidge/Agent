"""
Отдельный процесс Cloudflare quick tunnel (без перезапуска при правках бота).

Нужны ДВА терминала:
  1) Сначала (рекомендуется): python main.py — чтобы на 127.0.0.1:PORT слушал FastAPI.
  2) Затем: python run_cloudflared_tunnel.py — этот скрипт ЗАНИМАЕТ текущий терминал (пока
     он работает, в нём нельзя запустить main — откройте новую вкладку/окно терминала для main).

Переменные: PORT (по умолчанию 8000), CLOUDFLARED_BIN.

Публичный URL пишется в data/runtime/current_tunnel.txt — main.py читает его,
если EMBED_CLOUDFLARE_TUNNEL=false. Перезапускайте только main.py.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.tunnels.cloudflare_tunnel import (  # noqa: E402
    resolve_cloudflared_binary,
    try_extract_trycloudflare_url,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("run_cloudflared_tunnel")


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    local = f"http://127.0.0.1:{port}"
    exe = resolve_cloudflared_binary(os.environ.get("CLOUDFLARED_BIN"))
    if exe is None:
        sys.exit(1)

    out = _PROJECT_ROOT / "data" / "runtime" / "current_tunnel.txt"
    out.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Туннель к локальному серверу %s (остановка Ctrl+C). Файл для бота: %s",
        local,
        out,
    )
    logger.info(
        "Если backend ещё не запущен — откройте ДРУГОЙ терминал и выполните: python main.py "
        "(туннель ждёт процесс на %s). Этот терминал занят cloudflared.",
        local,
    )

    proc = subprocess.Popen(
        [str(exe), "tunnel", "--url", local],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            print(line, end="")
            url = try_extract_trycloudflare_url(line)
            if url:
                try:
                    out.write_text(url + "\n", encoding="utf-8")
                except OSError as exc:
                    logger.warning("Не удалось записать %s: %s", out, exc)
                else:
                    logger.info("Публичный URL: %s (main.py подхватит из файла)", url)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
