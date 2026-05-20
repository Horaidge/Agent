#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTENT_DIR="${ROOT_DIR}/projects/content"
RUN_SCRIPT="${CONTENT_DIR}/run_dev.sh"
ENV_FILE="${CONTENT_DIR}/.env"
RUNTIME_FILE="${CONTENT_DIR}/data/runtime/current_tunnel.txt"
DEFAULT_PORT="8000"

if [[ ! -d "${CONTENT_DIR}" ]]; then
  echo "Ошибка: не найден каталог ${CONTENT_DIR}" >&2
  exit 1
fi

if [[ ! -x "${RUN_SCRIPT}" ]]; then
  echo "Ошибка: не найден исполняемый скрипт ${RUN_SCRIPT}" >&2
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

echo "Soft restart (без перезапуска tunnel). PORT=${PORT}"
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

if [[ -f "${RUNTIME_FILE}" ]]; then
  TUNNEL_URL="$(tr -d '\r' < "${RUNTIME_FILE}" | awk 'NF {print; exit}')"
  if [[ -n "${TUNNEL_URL}" ]]; then
    echo "Текущий tunnel URL сохранён: ${TUNNEL_URL}"
  fi
fi

cd "${CONTENT_DIR}"
echo "Запускаем dev-режим без смены tunnel: ${RUN_SCRIPT}"
"${RUN_SCRIPT}" "$@"
