#!/usr/bin/env bash
# Перезапуск long polling мини-бота (после смены system override).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="data/bot_run.lock"
if [[ -f "$LOCK" ]]; then
  pid="$(head -1 "$LOCK" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 2
  fi
fi
nohup ./.venv/bin/python main.py >> data/bot.log 2>&1 &
