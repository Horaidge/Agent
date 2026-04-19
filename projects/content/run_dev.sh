#!/usr/bin/env bash
# Локальный запуск backend с гарантированно включённой dev-консолью /dev (переменная в окружении процесса).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export DEV_DEBUG_UI=true
# Автоперезапуск при правках .py (и др.) — после сохранения файла сервер поднимется заново.
export UVICORN_RELOAD=true
exec "${ROOT}/.venv/bin/python" main.py "$@"
