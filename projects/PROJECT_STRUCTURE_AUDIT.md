# Project structure audit: `/home/david/projects`

Дата: 2026-05-07. Только анализ; **перемещений и удалений не выполнялось.**

---

## 1. Текущее дерево верхнего уровня

```
/home/david/projects/
├── agent/                 # Next/VAPI frontend + локальный docker-compose
├── content/               # FastAPI production backend, бот, Gradio, dev UI, данные
└── content.placeholder-20260418/   # Заглушка/набросок структуры (не основной runtime)
```

Отдельно на хосте (не внутри `projects/`, но связано):

- [`/home/david/frontend`](/home/david/frontend) — Next под **корневой** [`docker-compose.yml`](/home/david/docker-compose.yml).
- [`/home/david/Agent-repo`](/home/david/Agent-repo) — ещё одна копия сценария агента.

---

## 2. Классификация по роли

### Production runtime (логический)

| Путь | Роль |
|------|------|
| **`projects/content/`** | FastAPI, Telegram webhook handlers, orchestration, Mongo access, Gradio `/ui`, dev console `/dev` (когда включено), prompts, services, storage. |
| **`projects/agent/app/`** | Пользовательский голосовой фронт (Next), VAPI public keys на build-time в Docker. |
| **Mongo** | Данные — либо том compose.projects (`content_mongo_data`), либо [`docker-compose.mongo.yml`](/home/david/docker-compose.mongo.yml) (`infra_mongo`). |

### Infrastructure / proxy (вне `projects`, но критично)

| Путь | Роль |
|------|------|
| [`/home/david/docker-compose*.yml`](/home/david) | Описание контейнеров и портов. |
| [`/home/david/nginx/`](/home/david/nginx) | Маршруты webhook, `/content/`, корень к agent, (в старом conf) отдельный frontend. |

### Experiments / temporary / ambiguous

| Путь | Заметки |
|------|---------|
| **`projects/content.placeholder-20260418/`** | Имя и дата указывают на **placeholder**; не отмечен как текущий прод. |
| **`/home/david/playgrounds/html/`** | HTML-прототипы (`live_*`, `lite_*`, `dev_*`, и т.д.); см. [`STATIC_HTML_USAGE_AUDIT.md`](/home/david/projects/STATIC_HTML_USAGE_AUDIT.md). |
| **`/home/david/docs/`** | Вспомогательные README (перенесены из корня: `README-FOR-LLM.md`, `README-VAPI.md`, `README-PROJECT-STRUCTURE.md`). |
| **`/home/david/frontend`** | Параллельный Next; может быть legacy вторым фронтом под корневой compose. |

### Крупные генерируемые / артефакты (не «исходники»)

| Путь | Заметки |
|------|---------|
| `projects/content/.venv/` | Локальное venv — восстановимо. |
| `projects/content/__pycache__/`, `**/node_modules/`, `**/.next/` | Кэш и зависимости. |
| `projects/content/data/` | **Runtime**: logs, uploads, tunnel runtime files — **критично для операций**, не для git. |

---

## 3. Что критично для runtime (нельзя ломать пути без миграции)

- **`projects/content/main.py`**, **`application.py`**, **`core/config/`**, **`bot/`**, **`services/`**, **`storage/`**, **`prompts/`** (если используются).
- **`projects/content/.env`** (секреты, `PORT`, Mongo, webhook, публичный URL).
- **Nginx upstream + пути webhook** согласованные с `WEBHOOK_PATH`.
- **`projects/agent/app`** как артефакт сборки + `projects/agent/config/.env` для VAPI keys в dev/docker.

---

## 4. Proposed clean structure (рекомендация на будущее, без действий)

Цель — уменьшить когнитивную нагрузку, **не меняя** сейчас путей:

| Будущее место | Что складывать |
|---------------|----------------|
| `projects/playgrounds/` (рекомендация) | **Уже создано:** [`/home/david/playgrounds/`](/home/david/playgrounds/) — HTML и архивы. Дальнейшие прототипы класть сюда. |
| `projects/archive/` | `content.placeholder-*`, устаревшие клоны, после явного решения. |
| Оставить в **корне `projects/`** только | `agent`, `content`, (опционально) `agent-next` после создания. |

**Корень репозитория `/home/david`** сейчас смешивает: compose, nginx, скрипты, прототипы HTML — в перспективе имеет смысл завести `infra/` или `deploy/`, но это отдельное решение с обновлением всех относительных путей в документации.

---

## 5. Новый workspace `projects/agent-next`

- **Безопасно создать** новый каталог **`/home/david/projects/agent-next`**: он не влияет на `agent/app`, `content`, Docker и VAPI, пока **не** добавлен в compose и nginx.
- **Этап 1:** локальная разработка (`pnpm dev` на свободном порту).
- **Этап 2 (после согласования):** отдельный сервис в compose или замена upstream для `/` — только с планом портов и zero-downtime.

Подробнее про порты и compose см. [`DOCKER_INFRASTRUCTURE_AUDIT.md`](/home/david/projects/DOCKER_INFRASTRUCTURE_AUDIT.md), раздел про agent-next.

---

*Конец документа.*
