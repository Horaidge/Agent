# Dream Viz — MVP (webhook → MongoDB → Gradio)

Модульный каркас: **Telegram (aiogram, webhook)** → **сервис** → **MongoDB** → **Gradio** для просмотра входящих сообщений. Long polling не используется.

## Структура

| Путь | Назначение |
|------|------------|
| `main.py` | Запуск uvicorn |
| `application.py` | Сборка FastAPI: lifespan, webhook, Gradio |
| `bot/` | Telegram: webhook HTTP, хендлеры, middleware, URL и управление webhook |
| `services/` | Бизнес-логика: сообщения, пайплайн, `services/observability/` — данные для dev UI |
| `ui/` | Gradio (`/ui`) + dev-консоль (`ui/dev/`, `/dev/`) |
| `storage/` | MongoDB (репозиторий, модели), пути и подготовка каталогов на диске |
| `core/` | Конфигурация (`core/config/`), ngrok (`core/tunnels/`), CLI webhook (`core/cli/`) |
| `run_cloudflared_tunnel.py` | **Отдельный процесс** Cloudflare quick tunnel → `data/runtime/current_tunnel.txt` (перезапуск `main.py` без смены URL) |
| `data/` | Логи, временные файлы, результаты (`logs/`, `temp/`, `outputs/`) |
| `core/observability/` | События для локальной dev-консоли (MongoDB + sanitize) |
| `ui/dev/` | Локальная **dev-консоль** (`/dev/`, только localhost): сообщения Mongo + ручная генерация Qwen Image |

## Локальная dev-консоль (наблюдение за ботом)

Включите в `ENV`: `DEV_DEBUG_UI=true`, перезапустите `python main.py`, откройте в браузере на этой машине:

`http://127.0.0.1:8000/dev/` (или ваш `PORT`).

Вкладка **Messages**: таблица входящих из MongoDB, клик — детали (текст, raw update JSON, trace: tools / model / errors из `observability_events`). Обновление таблицы — HTMX polling ~2.5 с. Вкладка **Generation**: форма вызывает `tool_generate_image` (без отображения API-ключей). Старый URL `/dev/debug/` перенаправляет на `/dev/`.

## Быстрый старт

1. Скопируйте `.env.example` в `ENV` или `.env`, заполните `TELEGRAM_BOT_TOKEN`, `MONGODB_URI` и URL webhook (см. ниже).

2. `pip install -r requirements.txt`

3. Запуск: `python main.py`

- **Health:** `GET http://127.0.0.1:8000/health`
- **Gradio:** `http://127.0.0.1:8000/ui`
- **Приём обновлений Telegram:** `POST` на путь из `WEBHOOK_PATH` (по умолчанию `/webhook`)

## Локальная разработка и HTTPS (туннель)

Telegram шлёт обновления только на **публичный HTTPS**. Пока у бота не выставлен `setWebhook` на такой URL, **сообщения до приложения не дойдут** — одного токена в `ENV` недостаточно.

### Вариант A — ngrok вместе с `main.py` (удобно для тестов)

1. Зарегистрируйтесь на [ngrok](https://ngrok.com/), откройте [Your Authtoken](https://dashboard.ngrok.com/get-started/your-authtoken) и скопируйте токен.
2. В `ENV`: `NGROK_AUTH_TOKEN=<токен>`, `START_NGROK_TUNNEL=true`, `WEBHOOK_PATH=/webhook`.
3. `pip install -r requirements.txt` (пакет `pyngrok` подтянет бинарник ngrok при первом запуске).
4. Запуск: `python main.py` — поднимется FastAPI, затем ngrok на ваш `PORT`, затем автоматически вызовется **setWebhook** на `https://<ваш-ngrok-домен>/webhook`.

В консоли будут строки с фактическим URL webhook; Gradio открывайте по `http://127.0.0.1:<PORT>/ui`.

### Вариант B — ngrok вручную (отдельный терминал)

1. Установите [ngrok](https://ngrok.com/), авторизуйтесь (`ngrok config add-authtoken ...`).
2. Запустите backend: `python main.py` (порт `8000` или ваш `PORT`).
3. В другом терминале: `ngrok http 8000` (или ваш порт).
4. Скопируйте выданный **HTTPS** URL, например `https://abcd-123.ngrok-free.app`.

В `ENV` задайте **полный** URL webhook (путь должен совпадать с `WEBHOOK_PATH`):

```env
WEBHOOK_PATH=/webhook
TELEGRAM_WEBHOOK_URL=https://abcd-123.ngrok-free.app/webhook
```

Либо без `TELEGRAM_WEBHOOK_URL`, только база:

```env
WEBHOOK_PATH=/webhook
PUBLIC_BASE_URL=https://abcd-123.ngrok-free.app
```

Тогда итоговый URL для Telegram будет `PUBLIC_BASE_URL` + `WEBHOOK_PATH`.

### Cloudflare Tunnel (cloudflared) — рекомендуется отдельный файл

Публичный URL меняется почти при каждом запуске quick tunnel; удобнее **не вшивать** туннель в `main.py`, а держать его в **отдельном процессе** — тогда можно много раз перезапускать бота, не трогая туннель.

1. Установите [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/). При необходимости в `ENV`: `CLOUDFLARED_BIN=C:\...\cloudflared.exe`.
2. В `ENV`: `EMBED_CLOUDFLARE_TUNNEL=false` (это **значение по умолчанию** в настройках), `SET_WEBHOOK_ON_STARTUP=true`, без `TELEGRAM_WEBHOOK_URL` / `PUBLIC_BASE_URL` (чтобы URL брался из туннеля автоматически).
3. Два терминала из корня проекта:
   - **Терминал 1** (оставить работать): `python run_cloudflared_tunnel.py` — в логах появится `https://....trycloudflare.com`, он же пишется в `data/runtime/current_tunnel.txt`.
   - **Терминал 2:** `python main.py` — приложение читает URL из файла и вызывает **setWebhook** на `https://....trycloudflare.com` + `WEBHOOK_PATH`.

Чтобы **обновить** публичный адрес: остановите `run_cloudflared_tunnel.py` (Ctrl+C), снова запустите его, затем один раз перезапустите `main.py` (или `python -m core.cli.webhook_cli set`).

**Опционально — всё в одном процессе:** `EMBED_CLOUDFLARE_TUNNEL=true` — тогда `cloudflared` стартует вместе с FastAPI внутри `main.py` (удобно для «одной кнопки», но каждый перезапуск приложения даёт новый туннель и новый URL).

Вручную без скрипта: `cloudflared tunnel --url http://127.0.0.1:8000`, затем скопируйте HTTPS в `TELEGRAM_WEBHOOK_URL` или `PUBLIC_BASE_URL` так же, как для ngrok.

### Установка webhook в Telegram

Токен и URL берутся из `ENV`. Из корня проекта:

```bash
python -m core.cli.webhook_cli set
```

Проверить текущий webhook:

```bash
python -m core.cli.webhook_cli info
```

Снять webhook:

```bash
python -m core.cli.webhook_cli delete
```

Опционально при старте приложения вызвать `setWebhook` автоматически: `SET_WEBHOOK_ON_STARTUP=true` и источник публичного URL — `data/runtime/current_tunnel.txt` (отдельный `run_cloudflared_tunnel.py`), встроенный туннель, либо `TELEGRAM_WEBHOOK_URL` / `PUBLIC_BASE_URL`.

Если задан `TELEGRAM_WEBHOOK_SECRET`, его нужно передавать в `setWebhook` (CLI делает это сам) — backend проверяет заголовок `X-Telegram-Bot-Api-Secret-Token`.

## Дальнейшее расширение

Реализации LLM, генерации изображений и анимации — в `services/llm/`, `services/images/`, `services/animation/`; оркестрация в `services/pipeline.py`. Вызов из `services/message_service.py` после сохранения в MongoDB.
