# Структура проектов на сервере

Корень: `/home/david`. Два независимых приложения:

| Проект | Путь | Роль |
|--------|------|------|
| **Агент** | `projects/agent/app` | Сайт на **Next.js** + **VAPI** (голосовой UI, лендинг). Это не Telegram-бот. |
| **Контент** | `projects/content` | **FastAPI**: Telegram-бот, webhook, LLM, Gradio `/ui`, dev-консоль `/dev`, пайплайн `/dream`, Mongo. |

Симлинк: `frontend_new_b_j8wlrsA3FhD` → `projects/agent/app` (удобство путей).

### MongoDB отдельно от приложений

Файл **`docker-compose.mongo.yml`** в корне `/home/david` поднимает только **MongoDB 7** с постоянным томом (`mongo_standalone_data`), порт **`127.0.0.1:27017`**.

```bash
cd /home/david
docker-compose -f docker-compose.mongo.yml up -d
```

В **`projects/content/.env`** для бота на **этой же машине** (без Docker):  
`MONGODB_URI=mongodb://127.0.0.1:27017`  
(имя БД и коллекции — как в вашем `settings`, по умолчанию те же, что и раньше).

Входящие сообщения и **метаданные видео** (имя файла, тип, подпись) пишутся в коллекцию **inbound_messages**; смотреть можно в **Gradio** `/content/ui` и в dev `/content/dev/`.

---

## Как это сходится на одном домене (`smartagentplatform.ru`)

Обычно перед приложениями стоит **nginx** (на хосте или в Docker). Схема маршрутов (см. `nginx/nginx.conf`):

- **`/`** → контейнер/процесс **Агента** (Next.js, порт вроде **3000** внутри, снаружи часто **3001**).
- **`/content/*`** → **Контент** (FastAPI, порт **8000** внутри): `/content/ui` (Gradio), `/content/dev/` (dev-консоль), `/content/health`.
- **`/telegram/webhook`** → тот же **Контент** (обновления Telegram).
- **`/content/dev/`** и **`/dev/`** — dev UI с basic-auth в nginx (если настроено).

Если контейнеры или процесс **Контента** не запущены, по URL `/content/...` будет **502 Bad Gateway** (nginx жив, upstream нет).

---

## ENV-файлы

### Агент

- Шаблон: `projects/agent/config/.env.example`
- Рабочий: `projects/agent/config/.env` (не коммитить)
- Для **локального** `pnpm dev` Next подхватывает `.env.local` в `app/` — удобно сделать ссылку:  
  `ln -sf ../config/.env projects/agent/app/.env.local`

Нужны как минимум **`NEXT_PUBLIC_VAPI_PUBLIC_KEY`** и **`NEXT_PUBLIC_VAPI_ASSISTANT_ID`** (вшиваются в клиентский бандл при сборке).

### Контент

- Шаблон: `projects/content/.env.example`
- Рабочий: `projects/content/.env` (Telegram, OpenAI, Mongo, `PUBLIC_BASE_URL`, webhook и т.д.)

`.env` между проектами **не смешивать**.

---

## Быстрая разработка: Агент без Docker

На машине с Node 20+ и **pnpm** (один раз: `sudo corepack enable`, если `/usr/bin` только под root):

```bash
cd /home/david/projects/agent/app
# один раз, если нет .env.local:
ln -sf ../config/.env .env.local
pnpm install
pnpm dev
```

По умолчанию: **http://127.0.0.1:3000**

С **другого компьютера** «localhost сервера» в браузере не открыть — используйте **SSH port forward** с ноутбука:

```bash
ssh -L 3000:127.0.0.1:3000 user@<сервер>
```

и откройте `http://localhost:3000` у себя. Либо **Port Forwarding** в Cursor/VS Code Remote.

Чтобы слушать все интерфейсы (редко нужно):  
`pnpm exec next dev -H 0.0.0.0 -p 3000`

---

## Контент: локально без Docker

```bash
cd /home/david/projects/content
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

По умолчанию uvicorn на **8000** (см. настройки). Для dev UI нужно **`DEV_DEBUG_UI=true`** в `.env`.

---

## Docker: общий стек под прод

Файлы: `docker-compose.projects.yml`, `nginx/nginx.projects.conf` (или актуальный `nginx/nginx.conf` у вас на хосте), `projects/content/Dockerfile`, `projects/agent/app/Dockerfile`.

Пример подъёма (ключи VAPI для сборки фронта берутся из env):

```bash
cd /home/david
set -a && source projects/agent/config/.env && set +a
docker-compose -f docker-compose.projects.yml build
docker-compose -f docker-compose.projects.yml up -d
```

Проверка:

```bash
docker ps
curl -I http://127.0.0.1/
curl -I http://127.0.0.1/content/health
```

Образы/имена контейнеров могли задаваться вручную (`david_content_1`, `david_frontend_new_1`, …) — смотрите `docker ps` и `nginx/*.conf`.

---

## Глобальная политика LLM (Контент)

Дополнительный системный слой для **всех** вызовов OpenAI в Контенте:  
`projects/content/prompts/global_model_policy.md` (редактируется вручную, без кеша).

Основной сценарий чат-бота: `projects/content/prompts/system_prompt.md`.

---

## Что такое `content.placeholder-20260418`

Резервная/временная копия. Рабочий код — только в **`projects/content`**.

---

## Мини-чеклист «всё поднято»

1. **Агент в проде**: контейнер Next или процесс `pnpm start`, nginx отдаёт `/`.
2. **Контент в проде**: процесс/контейнер на 8000, nginx — `/content/` и `/telegram/webhook`.
3. **Mongo** — если Контенту нужна БД.
4. Webhook Telegram указывает на публичный HTTPS URL до **`/telegram/webhook`**.
