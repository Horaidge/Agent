# Agent — голосовой сайт (Next.js + VAPI)

Фронтенд для голосового ассистента. Репозиторий **только** про сайт; Telegram-бот и бэкенд контента — в другом проекте.

## Структура

- `app/` — Next.js 16 (исходники, `pnpm`, Dockerfile)
- `config/` — пример переменных (`config/.env.example`). Скопируйте в `config/.env` и заполните ключи VAPI.
- `docker-compose.yml` — опциональный запуск в Docker (порт 3001)

## Быстрый старт (локально)

```bash
cd app
cp ../config/.env.example ../config/.env   # заполните NEXT_PUBLIC_VAPI_*
ln -sf ../config/.env .env.local             # или задайте переменные вручную
pnpm install
pnpm dev
```

Откройте http://localhost:3000

## Переменные

См. `config/.env.example`. Для сборки в Docker те же значения должны быть в `config/.env` (или переданы как build-args).
