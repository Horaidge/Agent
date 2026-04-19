# README FOR LLM

Этот документ предназначен для передачи в LLM как полный контекст по двум проектам в репозитории.
Цель: быстро объяснить модели, что это за система, как она запускается, где что находится, и какие есть важные технические ограничения.

---

## 1) Обзор системы

В корне `/home/david` находятся два независимых проекта:

1. `projects/agent/app` — **Agent UI** (Next.js + Vapi Web SDK).
2. `projects/content` — **Content Backend** (FastAPI + Telegram webhook + MongoDB + Gradio UI + Dev Console + Dream Pipeline).

Они могут запускаться:

- в Docker (через `docker-compose.projects.yml`),
- в dev-режиме как локальные процессы.

В прод/стейдж конфигурации домен обычно один (`smartagentplatform.ru`), а маршрутизация идет через nginx:

- `/` -> Agent UI,
- `/content/*` -> Content Backend,
- `/telegram/webhook` -> Telegram webhook endpoint backend.

---

## 2) Проект 1: Agent UI (`projects/agent/app`)

### Назначение

Фронтенд голосового интерфейса (voice-first) на Next.js.
Интеграция с Vapi для голосового ассистента.

### Основные технологии

- Next.js
- React
- TypeScript
- Framer Motion
- `@vapi-ai/web`

### Что делает

- Отображает голосовой UI (orb, статусы, транскрипт и т.п.).
- Инициирует/ведет голосовой диалог через Vapi.
- Может реагировать на tool-calls ассистента (например, показать/скрыть видео).

### Ключевые env переменные

- `NEXT_PUBLIC_VAPI_PUBLIC_KEY`
- `NEXT_PUBLIC_VAPI_ASSISTANT_ID`

Важно: это публичные ключи для клиентского приложения. Приватные API-ключи не должны попадать в `NEXT_PUBLIC_*`.

### Локальный dev запуск

```bash
cd /home/david/projects/agent/app
npm install
npm run dev
```

Обычно доступно на `http://localhost:3000`.

---

## 3) Проект 2: Content Backend (`projects/content`)

### Назначение

Бэкенд-проект с Telegram-ботом и пайплайном генерации:

- принимает Telegram updates через webhook,
- обрабатывает сообщения,
- сохраняет данные в MongoDB,
- выполняет этапы LLM/генерации (dream pipeline),
- предоставляет UI для наблюдения и отладки.

### Основные технологии

- FastAPI + Uvicorn
- aiogram (Telegram)
- MongoDB (motor + pymongo)
- Gradio (`/ui`)
- HTMX/Jinja templates в dev-консоли (`/dev/`)

### Главные endpoint-ы

- Health: `/health`
- Gradio UI: `/ui`
- Dev Console: `/dev/`
- Telegram webhook path задается env переменной `WEBHOOK_PATH` (часто `/telegram/webhook` в текущей схеме домена).

### Внутренние ключевые файлы

- `main.py` — запуск сервера.
- `application.py` — сборка приложения, lifecycle, роуты, индексы Mongo, интеграции.
- `core/config/settings.py` — конфигурация и env.
- `bot/*` — webhook/handlers/middleware.
- `services/*` — бизнес-логика (чат, пайплайны, генерация).
- `services/tools/` — **все инструменты модели в одном месте**:
  - `openai_definitions.py` — JSON-схемы function calling для OpenAI (`generate_image` и дальше по списку);
  - `image_tools.py`, `video_tools.py` — Python-реализации (вызов Qwen, Wan и т.д.);
  - оркестратор чата подключает список схем из `OPENAI_TOOLS_DEFAULT` и маппит имена на эти функции.
- `ui/dev/templates/*` — backend dev UI.

### Ключевая особенность конфигурации

В `core/config/settings.py` используется принудительная загрузка `ENV/env/.env` с `override=True`.
Это значит, что значения из `.env` проекта могут перекрывать переменные окружения из shell.

Практический вывод: если что-то "не подхватилось", сначала проверяйте `projects/content/.env`.

---

## 4) Dream Pipeline (внутри Content)

Dream Pipeline показывает по сценам последовательность:

1. План сцены (LLM)
2. Промпт к изображению
3. Сгенерированный кадр
4. Промпт к анимации
5. Видео-результат

UI пайплайна живет в dev-консоли.
Шаблон деталей: `ui/dev/templates/partials/dream_pipeline_detail.html`.

Недавнее UX-изменение: блок `JSON плана (этапы LLM)` теперь раскрыт по умолчанию (`<details open>`), чтобы не схлопывался неудобно при просмотре.

---

## 5) Режимы запуска

### A. Полностью локальный dev (без Docker)

#### Agent UI

```bash
cd /home/david/projects/agent/app
npm install
npm run dev
```

#### Content Backend

```bash
cd /home/david/projects/content
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Обычно backend слушает `8000`.

### B. Docker-режим

Используется `docker-compose.projects.yml`:

- `agent` (порт наружу обычно `127.0.0.1:3001 -> 3000`)
- `content` (внутренний порт `8000`)
- `mongo`
- `nginx` (публичный роутинг)

---

## 6) MongoDB: что важно

Content backend критично зависит от Mongo на старте (создает индексы в lifecycle).
Если Mongo недоступна, backend падает при startup.

Типичная ошибка: `ServerSelectionTimeoutError`.

Типичный источник проблемы:

- в `.env` стоит `MONGODB_URI=mongodb://mongo:27017` (это Docker DNS-имя),
- а backend запущен локально вне Docker и не видит имя `mongo`.

Решение: задать URI, доступный локальному процессу (например `mongodb://127.0.0.1:27017` или другой реальный адрес доступной Mongo).

---

## 7) ffmpeg и финальная склейка

Для финальной видео-склейки нужен системный `ffmpeg`.

Сейчас на хосте установлен и доступен в PATH.

Важно: если backend запускается в Docker-контейнере, `ffmpeg` должен быть установлен **внутри контейнера** через `Dockerfile`.
Текущий `projects/content/Dockerfile` изначально ставит только Python зависимости, поэтому ffmpeg туда нужно добавлять отдельно.

---

## 8) Вебхуки Telegram и публичный HTTPS

Telegram webhook требует публичный HTTPS URL.
Поддерживаются сценарии:

- статический публичный домен (`TELEGRAM_WEBHOOK_URL` / `PUBLIC_BASE_URL`),
- ngrok,
- cloudflared (встроенно или отдельным процессом).

При `SET_WEBHOOK_ON_STARTUP=true` backend пытается автоматически выставить webhook.

Проверять:

- логи старта (`setWebhook success/fail`),
- `python -m core.cli.webhook_cli info` (в `projects/content`).

---

## 9) Роутинг через nginx (важно для LLM)

Типовая схема:

- `/telegram/webhook` -> backend webhook endpoint
- `/content/*` -> backend (`/health`, `/ui`, `/dev/`, API)
- `/` -> agent frontend

Из-за этого один и тот же backend endpoint может иметь:

- локальный адрес: `http://127.0.0.1:8000/ui`
- публичный префиксный адрес: `https://<domain>/content/ui`

---

## 10) Что считать "нормальным состоянием системы"

Минимально рабочий набор:

1. Поднят MongoDB.
2. Поднят Content backend (`/health` -> ok).
3. Настроен и валиден Telegram webhook.
4. (Опционально) Поднят Agent UI.
5. Для видео-склейки доступен `ffmpeg` в среде, где реально выполняется склейка.

---

## 11) Чеклист для LLM перед любыми изменениями

1. Уточнить, какой проект меняем: `agent` или `content`.
2. Уточнить режим запуска: local dev или Docker.
3. Проверить фактические порты и процессы.
4. Для backend задач проверить доступность Mongo.
5. Для video pipeline проверить наличие `ffmpeg` в нужной среде (host/container).
6. Не полагаться на shell env для `content`, пока не проверен `projects/content/.env`.

---

## 12) Ограничения и правила безопасности

- Никогда не публиковать реальные секреты из `.env` (токены, API keys).
- В LLM-контекст передавать только имена переменных и структуру.
- Разделять публичные и приватные ключи:
  - `NEXT_PUBLIC_*` только для фронтенд-публичного.
  - приватные ключи только на backend.

---

## 13) Краткая карта репозитория

- `/home/david/projects/agent/app` — фронтенд Agent UI.
- `/home/david/projects/agent/config` — env-конфиг Agent.
- `/home/david/projects/content` — backend Telegram + pipeline.
- `/home/david/nginx` — nginx конфиги для маршрутизации проектов.
- `/home/david/docker-compose.projects.yml` — общий docker-stack двух проектов.

---

## 14) Рекомендуемый формат запроса к LLM (шаблон)

Можно давать модели такой префикс:

1. "Работаем с проектом: `content` или `agent`."
2. "Режим: local dev или docker."
3. "Текущая цель: (например, исправить dream pipeline UI / починить webhook / добавить шаг в генерацию)."
4. "Ограничения: не трогать секреты, не менять публичные маршруты без необходимости."

---

Этот файл является high-level onboarding-доком. За деталями по конкретным модулям см. README в соответствующих подпроектах и код.
