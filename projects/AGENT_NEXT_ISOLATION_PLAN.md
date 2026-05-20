# Agent-next isolation plan

Дата: 2026-05-07. **Не создаёт** каталог `agent-next` и **не** меняет runtime — только правила безопасной параллельной разработки.

---

## 1. Цель

Ввести новый procedural frontend в [`/home/david/projects/agent-next`](/home/david/projects/agent-next) **без** влияния на:

- работающий **agent** (`projects/agent/app`, порт **3001**),
- **content** (порт **8002**),
- **system nginx** и webhook **/telegram/**,
- **Mongo** production.

---

## 2. Рекомендуемый dev workflow (фаза 0)

1. **Только локальный Next:** `pnpm install` / `pnpm dev` **внутри `agent-next`**.
2. Порт из [`PORT_ALLOCATION_MAP.md`](/home/david/projects/PORT_ALLOCATION_MAP.md), например **`3002`** или **`3100`** — обязательно проверить `ss -tlnp` перед стартом.
3. **Отдельный env-файл:** `.env.local` **только** для agent-next; **не** symlink на `projects/agent/config/.env` и **не** копировать `projects/content/.env`.
4. Для будущих публичных ключей VAPI (когда интеграция будет явно запланирована) — использовать **sandbox assistant** и **отдельные** ключи, не те же, что в production agent-образе, пока нет формального sign-off.

---

## 3. Когда **не** нужен Docker для agent-next

- Пока нет требования «как в проде» для CI: **достаточно `pnpm dev` и `pnpm build` на хосте**.
- Пока **не** нужен общий nginx-маршрут с доменом — избегаем touch production ingress.

---

## 4. Когда может понадобиться отдельный compose

- Нужна **изолированная** среда с фиксированными версиями Node на другой машине.
- Нужен **stage** с TLS и своим vhost **без** изменения текущего `voice` (отдельный поддомен и **новый** vhost-файл — только после отдельного approval).

До этого момента: **не** добавлять сервис в [`docker-compose.projects.yml`](/home/david/docker-compose.projects.yml).

---

## 5. Изоляция от production env и данных

| Риск | Митигация |
|------|-----------|
| Случайно подхватить production Mongo | В agent-next **не** задавать `MONGODB_URI` от content; для моков — in-memory / локальная sqlite только если явно решено |
| Случайно использовать production Telegram/VAPI секреты | Отдельный `.env.local`; секреты не коммитить |
| Случайно дергать production API на `smartagentplatform.ru` | В dev использовать отдельный base URL или моки; любые вызовы к проду — явный флаг |

---

## 6. Будущие WebSocket / VAPI интеграции

- **WebSocket:** вынос в отдельный модуль с конфигом URL из **dev-only** env; дефолт — `undefined` / mock.
- **VAPI:** инициализация только после явного user gesture (как в типичных voice UIs); не автостарт при загрузке страницы в dev без необходимости.
- **CORS / cookie:** новый origin (другой порт) — учитывать, что backend может не принимать кросс-origin до настройки (пока backend **не** трогаем).

---

## 7. Проверка перед любыми инфраструктурными шагами

- Перечитать [`RUNTIME_SOURCE_OF_TRUTH.md`](/home/david/projects/RUNTIME_SOURCE_OF_TRUTH.md).
- Перечитать [`DEVELOPMENT_SAFETY_RULES.md`](/home/david/projects/DEVELOPMENT_SAFETY_RULES.md).
- Любое изменение nginx/docker — **отдельный** ticket + окно maintenance.

---

*Конец документа.*
