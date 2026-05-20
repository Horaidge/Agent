# Telegram-бот: запуск в dev и в контейнере

Бот работает **только через HTTPS webhook** (long polling не используется). FastAPI принимает `POST` на путь из `WEBHOOK_PATH`, обновление обрабатывает aiogram (`bot/webhook.py`, `application.py`).

## Обязательные переменные окружения

| Переменная | Назначение |
|------------|------------|
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather |
| `WEBHOOK_PATH` | Путь на вашем сервере, **с тем же суффиксом**, что и в итоговом URL webhook (например `/telegram/webhook`) |
| Публичный **HTTPS** URL | Telegram должен достучаться до `{PUBLIC_URL}{WEBHOOK_PATH}`. Локального `http://127.0.0.1` недостаточно без туннеля или reverse proxy с TLS |

Опционально:

- `TELEGRAM_WEBHOOK_SECRET` — тогда Telegram шлёт заголовок `X-Telegram-Bot-Api-Secret-Token`; без совпадения ответ будет 403.
- `TELEGRAM_PROXY_URL` — прокси только для вызовов Bot API (SOCKS5/HTTP).
- `SET_WEBHOOK_ON_STARTUP=true` — при старте приложения вызвать `setWebhook` (удобно в dev с меняющимся trycloudflare URL).

Приоритет сборки URL для `setWebhook` описан в `bot/webhook_url.py`: сначала живой URL Cloudflare quick tunnel (память или `data/runtime/current_tunnel.txt`), затем `TELEGRAM_WEBHOOK_URL`, затем `PUBLIC_BASE_URL` + `WEBHOOK_PATH`.

## Локальная разработка (рекомендуемый сценарий)

### Вариант A: один скрипт с хоста (туннель + backend)

Из каталога пользователя (пример):

```bash
~/dev-refresh-content.sh
```

Скрипт освобождает `PORT` из `projects/content/.env`, поднимает Cloudflare quick tunnel, пишет URL в `data/runtime/current_tunnel.txt`, затем запускает `projects/content/run_dev.sh`.

`run_dev.sh` выставляет `DEV_DEBUG_UI=true` и `UVICORN_RELOAD=true` и запускает `main.py` из venv проекта.

Условия:

- В `.env` проекта: `SET_WEBHOOK_ON_STARTUP=true`, `EMBED_CLOUDFLARE_TUNNEL=false` (туннель **отдельным** процессом, как делает скрипт).
- После старта в логах должны быть строки `setWebhook: успех` и `getWebhookInfo ... url='https://...'` с вашим `WEBHOOK_PATH`.

Проверки:

- `curl -sS http://127.0.0.1:8000/health` → `{"status":"ok"}`
- Dev UI: `http://127.0.0.1:8000/dev/` (только localhost, если включён `DEV_DEBUG_UI`).

### Вариант B: два терминала вручную

1. `cd projects/content && python run_cloudflared_tunnel.py` — дождаться URL в логе / в `data/runtime/current_tunnel.txt`.
2. `cd projects/content && ./run_dev.sh` или `python main.py`.

Если сначала поднять приложение **без** файла туннеля, автоматический `setWebhook` может не собрать URL — порядок как в варианте A.

### Вариант C: встроенный cloudflared в процессе `main.py`

В `.env`: `EMBED_CLOUDFLARE_TUNNEL=true` и при необходимости `START_CLOUDFLARE_TUNNEL=true` (см. комментарии в `.env.example`). Один процесс поднимает туннель и ждёт URL перед `setWebhook`. Удобно без отдельного скрипта, сложнее отлаживать сетевые сбои.

### Вариант D: ngrok

`START_NGROK_TUNNEL=true` и `NGROK_AUTH_TOKEN` — см. `core/tunnels/startup.py`. Подходит, если уже используете ngrok.

## Контейнер (Docker)

`Dockerfile` в корне проекта: образ на Python 3.12-slim, `ffmpeg`, `CMD ["python", "main.py"]`, порт **8000**.

Сборка (из корня репозитория `content`):

```bash
docker build -t dream-viz-content .
```

Запуск с файлом секретов (пример):

```bash
docker run --rm -p 8000:8000 --env-file .env dream-viz-content
```

Важно:

1. **MongoDB** должна быть доступна из контейнера: не `127.0.0.1` хоста, а `host.docker.internal`, IP хоста в Docker-сети или сервис в `docker compose` (`MONGODB_URI=...`).
2. **Telegram по-прежнему требует HTTPS.** Варианты:
   - Публичный домен с TLS (nginx, Caddy, облачный LB) → проксирование на `http://<container>:8000`, в Telegram указать `https://домен{WEBHOOK_PATH}`.
   - Туннель на **хосте**, проброс на контейнер: `cloudflared tunnel --url http://127.0.0.1:8000` при опубликованном порте контейнера на хост.
3. В продакшене часто `SET_WEBHOOK_ON_STARTUP=false`, а webhook выставляют один раз CI/CD или вручную, чтобы не дергать Bot API при каждом рестарте. В dev с trycloudflare удобнее `true`, чтобы URL и webhook совпадали после смены хоста туннеля.
4. **Не включайте** `UVICORN_RELOAD` в контейнере без необходимости (в образе по умолчанию его нет; в `run_dev.sh` он включается только для локалки).

## Частые проблемы

- **Бот молчит после смены trycloudflare URL** — перезапустите backend после того, как новый URL записан в `current_tunnel.txt`, с `SET_WEBHOOK_ON_STARTUP=true`, либо выставьте `TELEGRAM_WEBHOOK_URL` вручную и перезапустите.
- **Несовпадение пути** — в Telegram должен быть ровно `{база}{WEBHOOK_PATH}`; проверьте `.env` и `getWebhookInfo` в логах.
- **`POST /telegram/webhook` с пустым телом** может дать 5xx: ожидается валидный объект `Update` от Telegram, а не произвольный JSON.

## Безопасность

- Не коммитьте `.env` с реальными токенами.
- Ротация токена: новый токен в BotFather → обновить `TELEGRAM_BOT_TOKEN` и перезапуск.
