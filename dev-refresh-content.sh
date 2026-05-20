#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTENT_DIR="${ROOT_DIR}/projects/content"
RUN_SCRIPT="${CONTENT_DIR}/run_dev.sh"
TUNNEL_SCRIPT="${CONTENT_DIR}/run_cloudflared_tunnel.py"
ENV_FILE="${CONTENT_DIR}/.env"
RUNTIME_FILE="${CONTENT_DIR}/data/runtime/current_tunnel.txt"
TUNNEL_PID_FILE="${CONTENT_DIR}/data/runtime/dev-tunnel.pid"
TUNNEL_LOG_FILE="${CONTENT_DIR}/data/runtime/dev-tunnel.log"
DEFAULT_PORT="8000"
PYTHON_BIN=""

if [[ ! -d "${CONTENT_DIR}" ]]; then
  echo "Ошибка: не найден каталог ${CONTENT_DIR}" >&2
  exit 1
fi

if [[ ! -x "${RUN_SCRIPT}" ]]; then
  echo "Ошибка: не найден исполняемый скрипт ${RUN_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${TUNNEL_SCRIPT}" ]]; then
  echo "Ошибка: не найден скрипт туннеля ${TUNNEL_SCRIPT}" >&2
  exit 1
fi

read_port_from_env() {
  local file="$1"
  local line
  local key
  local value
  if [[ ! -f "${file}" ]]; then
    return 1
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    if [[ "${line}" == *=* ]]; then
      key="${line%%=*}"
      value="${line#*=}"
      key="${key//[[:space:]]/}"
      value="${value%%#*}"
      value="${value%"${value##*[![:space:]]}"}"
      value="${value#"${value%%[![:space:]]*}"}"
      if [[ "${key}" == "PORT" && -n "${value}" ]]; then
        echo "${value}"
        return 0
      fi
    fi
  done < "${file}"

  return 1
}

PORT="$(read_port_from_env "${ENV_FILE}" || true)"
PORT="${PORT:-${DEFAULT_PORT}}"

cleanup_tunnel() {
  if [[ -f "${TUNNEL_PID_FILE}" ]]; then
    local tunnel_pid
    tunnel_pid="$(<"${TUNNEL_PID_FILE}")"
    if [[ -n "${tunnel_pid}" ]] && kill -0 "${tunnel_pid}" 2>/dev/null; then
      kill "${tunnel_pid}" 2>/dev/null || true
    fi
    rm -f "${TUNNEL_PID_FILE}" || true
  fi
}

stop_old_tunnel_processes() {
  local pids

  if [[ -f "${TUNNEL_PID_FILE}" ]]; then
    local old_pid
    old_pid="$(<"${TUNNEL_PID_FILE}")"
    if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
      echo "Останавливаем прошлый tunnel pid из файла: ${old_pid}"
      kill "${old_pid}" 2>/dev/null || true
      sleep 1
      if kill -0 "${old_pid}" 2>/dev/null; then
        kill -9 "${old_pid}" 2>/dev/null || true
      fi
    fi
    rm -f "${TUNNEL_PID_FILE}" || true
  fi

  if command -v pgrep >/dev/null 2>&1; then
    pids="$(pgrep -f "run_cloudflared_tunnel.py" || true)"
    if [[ -n "${pids}" ]]; then
      echo "Останавливаем висящие run_cloudflared_tunnel.py: ${pids}"
      kill ${pids} 2>/dev/null || true
    fi

    pids="$(pgrep -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" || true)"
    if [[ -n "${pids}" ]]; then
      echo "Останавливаем висящие cloudflared для порта ${PORT}: ${pids}"
      kill ${pids} 2>/dev/null || true
    fi
  fi
}

wait_for_tunnel_url() {
  local timeout_sec="${1:-45}"
  local started_at now line
  started_at="$(date +%s)"

  while true; do
    if [[ -f "${RUNTIME_FILE}" ]]; then
      while IFS= read -r line || [[ -n "${line}" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        if [[ "${line}" =~ ^https://[a-zA-Z0-9-]+\.trycloudflare\.com$ ]]; then
          echo "${line}"
          return 0
        fi
      done < "${RUNTIME_FILE}"
    fi

    now="$(date +%s)"
    if (( now - started_at >= timeout_sec )); then
      return 1
    fi
    sleep 1
  done
}

if [[ -x "${CONTENT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${CONTENT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "Ошибка: не найден Python (ожидался .venv/bin/python, python3 или python)." >&2
  exit 1
fi

echo "Используем PORT=${PORT}"
echo "Проверяем, занят ли порт ${PORT}..."

PIDS=""
if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN || true)"
elif command -v fuser >/dev/null 2>&1; then
  PIDS="$(fuser -n tcp "${PORT}" 2>/dev/null || true)"
fi

if [[ -n "${PIDS}" ]]; then
  echo "Останавливаем процессы на порту ${PORT}: ${PIDS}"
  kill ${PIDS} || true

  for _ in {1..10}; do
    sleep 0.5
    if command -v lsof >/dev/null 2>&1; then
      STILL_RUNNING="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN || true)"
    elif command -v fuser >/dev/null 2>&1; then
      STILL_RUNNING="$(fuser -n tcp "${PORT}" 2>/dev/null || true)"
    else
      STILL_RUNNING=""
    fi
    [[ -z "${STILL_RUNNING}" ]] && break
  done

  if [[ -n "${STILL_RUNNING:-}" ]]; then
    echo "Порт ${PORT} всё ещё занят, завершаем принудительно: ${STILL_RUNNING}"
    kill -9 ${STILL_RUNNING} || true
  fi
else
  echo "Порт ${PORT} свободен."
fi

echo "Перезапускаем Cloudflare tunnel..."
mkdir -p "${CONTENT_DIR}/data/runtime"
stop_old_tunnel_processes
rm -f "${RUNTIME_FILE}"

(
  cd "${CONTENT_DIR}"
  "${PYTHON_BIN}" "${TUNNEL_SCRIPT}" > "${TUNNEL_LOG_FILE}" 2>&1
) &
NEW_TUNNEL_PID="$!"
echo "${NEW_TUNNEL_PID}" > "${TUNNEL_PID_FILE}"

sleep 1
if ! kill -0 "${NEW_TUNNEL_PID}" 2>/dev/null; then
  echo "Ошибка: не удалось запустить Cloudflare tunnel. Лог: ${TUNNEL_LOG_FILE}" >&2
  exit 1
fi

echo "Ждём публичный URL tunnel..."
if ! TUNNEL_URL="$(wait_for_tunnel_url 60)"; then
  echo "Ошибка: tunnel не выдал trycloudflare URL за 60 секунд. Лог: ${TUNNEL_LOG_FILE}" >&2
  exit 1
fi
echo "Tunnel готов: ${TUNNEL_URL}"

cd "${CONTENT_DIR}"
echo "Запускаем свежий dev-режим: ${RUN_SCRIPT}"
trap cleanup_tunnel EXIT INT TERM
"${RUN_SCRIPT}" "$@"
