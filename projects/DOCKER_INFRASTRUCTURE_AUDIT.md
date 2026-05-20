# Docker / reverse-proxy infrastructure audit

Дата аудита: 2026-05-07. Область: репозиторий хоста `/home/david` (без изменений конфигурации).

## 1. Обнаруженные compose-файлы

| Файл | Назначение (по содержимому) |
|------|------------------------------|
| [`/home/david/docker-compose.yml`](/home/david/docker-compose.yml) | Отдельный стек: **nginx:8080** → **frontend** (сборка `./frontend`) + **backend** (`image: david_backend`, `env_file: ./config/.env`). Только **nginx** монтирует конфиг с хоста. |
| [`/home/david/docker-compose.projects.yml`](/home/david/docker-compose.projects.yml) | Стек **smartagentplatform.ru**: **nginx:80**, **agent** (Next из `./projects/agent/app`), **content** (FastAPI из `./projects/content`), **mongo:7** + том `content_mongo_data`. |
| [`/home/david/docker-compose.mongo.yml`](/home/david/docker-compose.mongo.yml) | Автономный **MongoDB** на `127.0.0.1:27017`, `container_name: infra_mongo`, том `mongo_standalone_data`. |
| [`/home/david/projects/agent/docker-compose.yml`](/home/david/projects/agent/docker-compose.yml) | Локальный **только agent**: сервис `agent-frontend`, порты **3001:3000**. |
| [`/home/david/Agent-repo/docker-compose.yml`](/home/david/Agent-repo/docker-compose.yml) | Дубликат сценария агента (как `projects/agent/docker-compose.yml`). |

**Важно:** в репозитории сосуществуют **несколько стеков**. Какой из них сейчас «production» на хосте, определяется тем, какой `docker compose` реально запущен и какой `nginx.conf` подключён к системному nginx — это вне кода и здесь только зафиксировано как **риск путаницы**.

---

## 2. Карта контейнеров (по `docker-compose.projects.yml`)

Имена сервисов внутри user-defined network Compose (логические DNS-имена):

| Сервис | Образ / build | Host ports | Зависимости | restart |
|--------|----------------|------------|-------------|---------|
| **nginx** | `nginx:alpine` | **80:80** | `agent`, `content` | `unless-stopped` |
| **agent** | build `projects/agent/app` | **127.0.0.1:3001:3000** | — | `unless-stopped` |
| **content** | build `projects/content` | **127.0.0.1:8002:8002** | `mongo` | `unless-stopped` |
| **mongo** | `mongo:7` | (внутренний) | том `content_mongo_data` | `unless-stopped` |

**Сети:** явная секция `networks` в файле не задана — используется default network проекта Compose.

**Контейнер без фиксированного `container_name`** (кроме mongo в *другом* файле): фактические имена вида `{project}_{service}_1` зависят от имени директории/проекта compose.

---

## 3. Volumes и bind mounts

### `docker-compose.projects.yml`

- **Именованные тома:** `content_mongo_data` → Mongo `/data/db`.
- **Bind mounts:** **отсутствуют** у сервисов `agent` и `content`. Код попадает в образ через **`COPY`** в Dockerfile → изменения на хосте **не** попадают в уже собранный контейнер без **rebuild**.

### `docker-compose.mongo.yml`

- Том: `mongo_standalone_data` → `/data/db`.
- Порт: `127.0.0.1:27017:27017`.

### Корневой `docker-compose.yml` (frontend + backend)

| Том / mount | Описание |
|-------------|----------|
| `./nginx/nginx.conf` | **:ro** → `/etc/nginx/nginx.conf` |
| `./nginx/.htpasswd` | **:ro** (basic auth) |
| *(сервисы frontend/backend)* | монтирования исходников **нет** в compose — только build. |

### Сопоставление с «живым» nginx на хосте

Файл [`/home/david/nginx/nginx.conf`](/home/david/nginx/nginx.conf) использует **хардкод upstream-имён Docker:**

- `david_content_1:8000`
- `david_frontend_new_1:3000`

Это **не** совпадает с DNS-именами сервисов из `docker-compose.projects.yml` (`content`, `agent`). Значит, либо:

- используется **другой** compose-проект / override, либо
- контейнеры переименованы вручную, либо
- конфиг **устарел** относительно `nginx.projects.conf`.

[`/home/david/nginx/nginx.projects.conf`](/home/david/nginx/nginx.projects.conf) согласован с `docker-compose.projects.yml`: переменные `$content_upstream` → `content:8000`, `$agent_upstream` → `agent:3000`.

---

## 4. Dockerfile — рабочие каталоги и порты

### [`projects/content/Dockerfile`](/home/david/projects/content/Dockerfile)

- `WORKDIR /app`
- `COPY . .` (весь контекст `projects/content`)
- `EXPOSE **8000**`
- `CMD ["python", "main.py"]` — порт берётся из **Settings.port** (по умолчанию **8000**, см. `core/config/settings.py`).

**Замечание по согласованности:** в `docker-compose.projects.yml` опубликовано **`8002:8002`**. Если внутри контейнера приложение слушает **8000** (значение по умолчанию из `.env.example`: `PORT=8000`), публикация должна быть вида **`8002:8000`**, иначе с хоста не будет ответа на ожидаемом порту. Перед любыми правками нужно **проверить реальный `PORT` в `projects/content/.env` в среде деплоя** (файл не читался в аудите). Это аудиторский риск, не инструкция к изменению.

### [`projects/agent/app/Dockerfile`](/home/david/projects/agent/app/Dockerfile)

- Multi-stage: deps → builder (`pnpm build`) → runner **standalone** Next.
- `WORKDIR /app`, `EXPOSE 3000`, `CMD ["node", "server.js"]`.
- VAPI: build-args `NEXT_PUBLIC_VAPI_*` зашиваются на этапе **build**.

### [`frontend/Dockerfile`](/home/david/frontend/Dockerfile)

- Аналогичный standalone Next (другой фронт под корневой `docker-compose.yml`).

---

## 5. Telegram webhook / туннели (с точки зрения маршрутизации)

- **`nginx.projects.conf`:** `location = /telegram/webhook` → прокси на **`http://content:8000/webhook`** (комментарий: задать `WEBHOOK_PATH=/webhook` в `projects/content/.env`).
- **`nginx.conf`:** `location = /telegram/webhook` → **`http://david_content_1:8000/telegram/webhook`** (путь **другой** — `/telegram/webhook` на бэкенде).

В коде по умолчанию FastAPI регистрирует путь из **`webhook_path`** (дефолт **`/webhook`** в settings). **Несовпадение путей между двумя nginx-конфигами** — критично для работы webhook; при смене конфига без сверки с `.env` можно отключить бота. **В рамках аудита конфиги не менялись.**

Туннели Cloudflare/ngrok не описаны в compose; логика на хосте — см. скрипты в разделе **Runtime Scripts Audit**.

---

## 6. Что относится к какому продукту

| Компонент | docker-compose.projects.yml | Примечание |
|-----------|------------------------------|------------|
| **content** (FastAPI, Telegram, Gradio, `/dev`, Mongo) | сервис `content` + `mongo` | VAPI/WebRTC **не** в этом образе; интеграция VAPI — на **agent**. |
| **agent/app** (Next, голос, VAPI SDK) | сервис `agent` | Сборка с `NEXT_PUBLIC_VAPI_*`. |
| **Mongo** | `mongo` + том | Альтернатива: `docker-compose.mongo.yml` — отдельный инстанс. |
| **nginx** | сервис `nginx` | Маршрутизация домена / `/content/` / webhook / корень → agent. |
| **Туннели / webhooks** | вне compose | Скрипты Python + runtime-файлы под `projects/content/data/runtime/`. |

---

## 7. Критичные каталоги на хосте (без bind mount в projects compose)

Для стека **compose.projects** изменения на диске **сразу в рантайме контейнера** для `content`/`agent` **не** применяются — нужен rebuild/restart образа.

Для **локального** `run_dev.sh` (см. ниже) критично:

- [`/home/david/projects/content`](/home/david/projects/content) — весь Python-бэкенд, `.env`, `prompts/`, `data/`.
- Особенно: **`projects/content/.env`**, **`projects/content/data/`** (uploads, logs, runtime tunnel url).

**Нельзя произвольно переносить** без обновления путей в докерах, systemd, nginx и env: `MONGODB_URI`, `PUBLIC_BASE_URL`, `WEBHOOK_PATH`, `GRADIO_PROXY_PREFIX`, пути к данным.

---

## 8. Hot reload / live mounts

| Режим | Есть ли bind mount к коду? | Эффект правок на хосте |
|--------|---------------------------|-------------------------|
| `docker-compose.projects.yml` (agent, content) | **Нет** | Только после **пересборки** образа (кроме томов данных у Mongo). |
| Локальный **`projects/content/run_dev.sh`** | N/A (не Docker) | **`UVICORN_RELOAD=true`** — правки `.py` перезапускают процесс; **мгновенно влияет** на runtime этого процесса. |
| Корневой **`docker-compose.yml`** | Только nginx config | Правки **`nginx/nginx.conf`** попадают при рестарте nginx-контейнера. |

---

## Runtime Scripts Audit

### [`/home/david/dev-refresh-content.sh`](/home/david/dev-refresh-content.sh)

- **Docker Compose:** не вызывает.
- **Читает:** `projects/content/.env` (ключ `PORT`, иначе default **8000**).
- **Делает:** освобождает порт → перезапускает **Cloudflare tunnel** (`run_cloudflared_tunnel.py`, лог/PID в `projects/content/data/runtime/`) → запускает **`projects/content/run_dev.sh`**.
- **Трогает сервисы:** процессы на `PORT` на хосте, tunnel, **локальный** uvicorn через `run_dev.sh`.
- **Риск:** жёстко убивает процессы на выбранном порту; **не** останавливает dockerized content, если он слушает другой интерфейс.

### [`/home/david/dev-restart-content-soft.sh`](/home/david/dev-restart-content-soft.sh)

- **Docker Compose:** не вызывает.
- **Читает:** `projects/content/.env` (`PORT`), опционально показывает `data/runtime/current_tunnel.txt`.
- **Делает:** kill на `PORT` → **`run_dev.sh`** **без** перезапуска tunnel.
- **Трогает:** только локальный dev backend на хосте.

### [`/home/david/projects/content/run_dev.sh`](/home/david/projects/content/run_dev.sh)

- **Docker:** не использует.
- **Env:** `DEV_DEBUG_UI=true`, `UVICORN_RELOAD=true`.
- **Запуск:** `exec .venv/bin/python main.py`.
- **Итог:** dev-консоль `/dev` включена; **горячая перезагрузка Python**.

**Вывод:** «живые» правки, влияющие на работающий stack, в первую очередь относятся к **хостовому** режиму `run_dev.sh`, а не к образам compose.projects без bind mount.

---

## 9. Безопасное создание `projects/agent-next` (кратко)

См. также [`PROJECT_STRUCTURE_AUDIT.md`](/home/david/projects/PROJECT_STRUCTURE_AUDIT.md).

- **Новая папка** `/home/david/projects/agent-next` **не затрагивает** текущий `agent/app`, `content`, существующие compose-файлы и nginx, пока **не** добавлена в compose и **не** прописана в nginx.
- **Порты:** для локального `pnpm dev` разумно избегать **3001** (занят под agent в compose) и **3000** (часто default); кандидаты: **3002**, **3100**, **4321** — проверить `ss -tlnp` на хосте.
- **Рекомендация этапа 1:** только **`pnpm dev`** на отдельном порту; отдельный compose для agent-next — **после** согласования портов и маршрутов, чтобы не пересечься с `agent:3000` / системным прокси.

---

*Конец документа. Изменений в Docker, nginx и runtime не выполнялось.*
