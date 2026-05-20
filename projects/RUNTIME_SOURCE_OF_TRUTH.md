# Runtime Source of Truth

Документ зафиксирован: **2026-05-07**. Только наблюдение; конфигурация **не менялась**.

Цель: зафиксировать **фактическую** топологию production runtime на хосте, а не предположения по файлам в репозитории.

---

## 1. Активный Docker Compose

| Параметр | Значение (по `docker inspect` labels) |
|----------|----------------------------------------|
| **Файл конфигурации** | [`/home/david/docker-compose.projects.yml`](/home/david/docker-compose.projects.yml) |
| **Имя проекта Compose** | `david` |
| **Версия Compose (legacy)** | `1.29.2` (`docker-compose`) |
| **Рабочая директория проекта** | `/home/david` |

Сервис **`nginx`**, описанный в том же `docker-compose.projects.yml`, **не входит в список запущенных контейнеров** (на момент снимка). Публичный HTTP(S) обрабатывает **nginx ОС**, см. ниже.

---

## 2. Активный nginx

| Параметр | Значение |
|----------|----------|
| **Реальный конфиг vhost** | **`/etc/nginx/sites-enabled/voice`** на хосте |
| **Домен** | `smartagentplatform.ru`, `www.smartagentplatform.ru` |
| **TLS** | Certbot, порт **443** |
| **Порт 80** | В этом vhost для указанного `server_name` отдаётся **404** (редиректы на HTTPS в других server-блоках Certbot) — см. фактический файл на сервере |

Файлы в репозитории [`/home/david/nginx/nginx.conf`](/home/david/nginx/nginx.conf) и [`nginx.projects.conf`](/home/david/nginx/nginx.projects.conf) описывают **альтернативные/legacy** схемы (Docker nginx или старые имена контейнеров). **Фактический ingress** для домена — **`sites-enabled/voice`**.

---

## 3. Запущенные контейнеры (снимок)

| Имя контейнера | Образ (логическое имя) | Compose-сервис | Публикация портов на хост |
|----------------|-------------------------|----------------|---------------------------|
| `david_content_1` | `david_content` | `content` | `127.0.0.1:8002` → **8002** (внутри контейнера приложение слушает `PORT`, см. env) |
| `david_agent_1` | `david_agent` | `agent` | `127.0.0.1:3001` → **3000** |
| `david_mongo_1` | `mongo:7` | `mongo` | **Нет** привязки к порту хоста (только внутренняя сеть `david_default`) |

---

## 4. Источники переменных окружения (без значений секретов)

### Сервис `content`

- **Файл на хосте:** `env_file` в compose указывает на [`projects/content/.env`](/home/david/projects/content/.env).
- **Переопределения из compose:** блок `environment:` в `docker-compose.projects.yml` (например `MONGODB_URI`, `PUBLIC_BASE_URL`, `GRADIO_PROXY_PREFIX`, `UVICORN_RELOAD`).
- **Фактически в контейнере (имена, не значения):** задаются ключи для Telegram, webhook, Mongo, LLM, dev UI, Gradio и др. Критичные для маршрутизации:
  - **`PORT`** — на снимке задан **8002** (согласован с publish `8002:8002`).
  - **`WEBHOOK_PATH`** — на снимке **`/telegram/webhook`**.
  - **`TELEGRAM_WEBHOOK_URL`** — полный публичный HTTPS URL (для Bot API).
  - **`PUBLIC_BASE_URL`**, **`GRADIO_MOUNT_PATH`**, **`GRADIO_PROXY_PREFIX`** — префиксы UI.
  - **`MONGODB_URI`** — внутри compose-сети к сервису `mongo`.

Секреты (токены бота, API keys, пароли basic auth) **не копировать в документацию** — только хранение в `.env` / секрет-менеджере.

### Сервис `agent`

- **Файл:** [`projects/agent/config/.env`](/home/david/projects/agent/config/.env) (как `env_file` в compose).
- **VAPI:** публичные ключи часто зашиваются **на этапе `docker build`** через `build.args` (`NEXT_PUBLIC_*`); рантайм-переменные в контейнере могут не отражать все NEXT_PUBLIC значения.

### Сервис `mongo`

- Конфигурация по образу; данные на томе **`david_content_mongo_data`** → `/data/db`.

---

## 5. Активные маршруты (host nginx → backend)

По **`/etc/nginx/sites-enabled/voice`**:

| Публичный путь | Upstream (локально) | Назначение |
|----------------|---------------------|------------|
| **`/`** | `http://127.0.0.1:3001` | Next.js **agent** (голосовой фронт) |
| **`/content/`** | `http://127.0.0.1:8002/` | FastAPI + Gradio под префиксом (rewrite `/content/foo` → backend `/foo`) |
| **`/ui/`** | `http://127.0.0.1:8002/ui/` | Короткий публичный путь к Gradio UI |
| **`/dev/`** | `http://127.0.0.1:8002/dev/` | Dev-консоль content (долгие таймауты) |
| **`/telegram/`** | `http://127.0.0.1:8002/telegram/` | Webhook и прочие пути `/telegram/*` на FastAPI |

**Вывод по webhook:** внешний путь вида **`https://<домен>/telegram/webhook`** проксируется на **`127.0.0.1:8002/telegram/webhook`**, что **согласуется** с `WEBHOOK_PATH=/telegram/webhook` в контейнере (в отличие от дефолта `/webhook` в коде settings без переопределения).

---

## 6. VAPI / WebRTC

- Интеграция выполняется **в браузере** со стороны фронтенда (**agent**), с обращением к облачному VAPI.
- Отдельного локального «VAPI-порта» на хосте нет; используются **HTTPS** с домена и внешние endpoints SDK.
- Учёт ключей: см. build-args agent и документацию проекта (не дублировать ключи в git/docs).

---

## 7. Туннели

- В контейнере **content** на снимке: **`START_CLOUDFLARE_TUNNEL` / `START_NGROK_TUNNEL` отключены** — production webhook опирается на **публичный домен + host nginx**, а не на trycloudflare/ngrok внутри контейнера.
- Для **локальной разработки** на хосте отдельно существуют скрипты (см. [`DOCKER_INFRASTRUCTURE_AUDIT.md`](/home/david/projects/DOCKER_INFRASTRUCTURE_AUDIT.md)) и файлы под **`projects/content/data/runtime/`** — это **не обязательно** активно в production snapshot.

---

## 8. Расхождение «файл в репо» vs «факт в runtime»

| Тема | В репозитории | Фактически |
|------|----------------|------------|
| Обратный прокси | `docker-compose.projects.yml` содержит сервис `nginx` + `nginx.projects.conf` | Запущены только **agent, content, mongo**; прокси — **system nginx `voice`** |
| Порт content | Комментарий в compose про `8002:8000` | В runtime **`8002:8002`** и `PORT=8002` в контейнере |
| Старый `nginx/nginx.conf` | Имена `david_content_1:8000` и путь webhook | **Не используется** как SoT, если активен `sites-enabled/voice` |

---

## 9. Container graph (логический)

```
Internet (HTTPS)
    → host nginx (/etc/nginx/sites-enabled/voice)
        → 127.0.0.1:3001 (docker: david_agent_1)
        → 127.0.0.1:8002 (docker: david_content_1)
Telegram Bot API → https://smartagentplatform.ru/telegram/webhook
    → host nginx /telegram/
        → 127.0.0.1:8002/telegram/…
david_content_1 → mongodb://mongo:27017 → david_mongo_1 (volume david_content_mongo_data)
```

---

*Конец документа. Секреты намеренно не процитированы.*
