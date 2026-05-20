# Стратегия переменных окружения (ENVIRONMENT_STRATEGY)

Документ задаёт **правила владения**, **границу public/private**, **shared**‑сборки и разделение **production / experimental**. Цель — согласованные решения без дублирования смысла и без утечек.

Детальная «карта путей»: [`ENVIRONMENT_MAP.md`](ENVIRONMENT_MAP.md).

---

## 1. Принципы

1. **Одна переменная — один источник правды.** Дубликаты в нескольких файлах допустимы только осознанно (см. §5).
2. **Клиент браузера не доверяем.** Всё, что не должно светиться в бандле, **не** префиксуется `NEXT_PUBLIC_` и **не** кладётся во фронтовые `.env`, на которые рассчитан публичный билд.
3. **`.env.example`** — только шаблоны без значений; в git **никогда** реальные секреты.
4. **Production** — это зафиксированный runtime (Docker / system nginx / внешний домен). **Experimental** — локальный `agent-next`, отдельные ассистенты, моки, флаги dev.

---

## 2. Кто владеет какими env

| Владелец (логический) | Физический носитель | Ответственность |
|-------------------------|---------------------|-----------------|
| **Voice / web frontend (agent)** | [`projects/agent/config/.env`](agent/config/.env), при локальном запуске ещё [`projects/agent/app/.env.local`](agent/app/.env.local) | VAPI **публичные** ключи для Next, `docker-compose` build-args для образа `agent`, согласованность с доменом при необходимости |
| **Experimental frontend (agent-next)** | [`projects/agent-next/.env.local`](agent-next/.env.local) (или symlink на `agent/config/.env`) | Только то, что нужно **этому** Next; не размывать с backend‑секретами |
| **Backend / bot / AI pipelines (content)** | [`projects/content/.env`](content/.env) + override в compose (`environment:`) | Telegram, Mongo, LLM keys, webhook URL, `PUBLIC_BASE_URL`, dev‑флаги консоли и т.д. |
| **Инфраструктура хоста** | systemd, `/etc/nginx/`, секреты CI (вне репозитория) | TLS, апстримы, то, что не выносится в приложение |

Итог: **два основных «сейфа» приложения** — **`agent/config` (+ фронтовые `.env.local`)** и **`content/.env`**. Между ними переменные **не смешивают** без явной нужды.

---

## 3. Public vs private

### Public (к клиенту допустимо)

- В Next: переменные с префиксом **`NEXT_PUBLIC_`**.  
  Попадают в **клиентский бандл**; считайте, что их видит любой пользователь сайта.
- Типичные примеры по смыслу (имена, не значения): публичный ключ VAPI, id ассистента, базовый URL публичного API **если он предназначен для браузера**.

**Правило:** в `NEXT_PUBLIC_*` кладём только то, что по контракту провайдера **должно** жить на клиенте (как публичный ключ VAPI).

### Private (только сервер / только закрытые среды)

- Всё в **`projects/content/.env`**, что относится к **боту**, **Mongo**, **провайдерам LLM**, **секретам webhook**, **сервисным ключам**.
- Любые ключи **без** `NEXT_PUBLIC_` в Next — доступны на **серверной** части Next (RSC, route handlers, middleware), но **не** должны попадать в клиентский JS. Для `agent-next` foundation‑стадии серверных секретов **нет** — не добавлять «на будущее» в общий файл с VAPI без политики.

**Правило:** если значение утёкло бы в DevTools → это либо осознанный public (`NEXT_PUBLIC_*`), либо ошибка.

---

## 4. Shared (общее между компонентами)

| Что shared | Как |
|------------|-----|
| **Один набор `NEXT_PUBLIC_VAPI_*` для старого и нового Next** | Канон: [`projects/agent/config/.env`](agent/config/.env); для [`agent-next`](agent-next/) — **symlink** `.env.local` → `../agent/config/.env` (если состав переменных совместим) |
| **Имена переменных между dev и Docker** | Те же ключи, разные файлы: локально `.env`, в compose `env_file` + при необходимости `environment:` |
| **Документация** | [`*.env.example`](agent/config/.env.example) — только имена и комментарии |

**Не считать shared:** строки `content` и `agent` в одном файле без разделения — смешение увеличивает риск утечки и путаницу при experimental фронте.

---

## 5. Production only

Применимо к **задеплоенному** стеку (см. `RUNTIME_SOURCE_OF_TRUTH.md`):

- **Образ `agent`:** `NEXT_PUBLIC_*` часто **зашиваются на этапе `docker build`** (build-args); смена ключей требует **пересборки**, не только рестарта.
- **Контейнер `content`:** `PUBLIC_BASE_URL`, `TELEGRAM_WEBHOOK_URL`, `WEBHOOK_PATH`, `MONGODB_URI`, ключи провайдеров, флаги prod (например отключён `UVICORN_RELOAD`).
- **Системный nginx / TLS** — не в `.env` приложения, но относятся к production ingress.

**Правило:** production‑значения не копируют в репозиторий и не кладут в `.env.example`. Экспериментальные фронты **по политике безопасности** могут использовать **те же** публичные VAPI ключи, что и прод (осознанный риск), или **отдельный** assistant — тогда отдельный блок в `agent-next/.env.local` (experimental only).

---

## 6. Experimental only

- **[`projects/agent-next`](agent-next/):** локальный `pnpm dev` (например порт **3100**), отдельный билд, **не** подключён к production nginx, пока вы явно не решите иначе.
- Допустимо: отдельный **assistant id**, отключённые интеграции, моки backend, флаги `NODE_ENV=development`.
- **Не смешивать** с content `.env`: не подкладывать Mongo/Telegram в фронтовый env «для удобства».

**Правило:** всё, что относится только к черновому UI, живёт в **`agent-next`** или в отдельном файле, который **не** читает production backend.

---

## 7. Чеклист перед изменением env

- [ ] Это **public** или **private**? Нужен ли префикс `NEXT_PUBLIC_`?
- [ ] Кто **владелец** файла: agent, agent-next или content?
- [ ] Это **shared** через symlink или намеренный дубликат?
- [ ] Затрагивает ли изменение **production** (пересборка образа / рестарт / ротация ключей)?
- [ ] Обновлён ли **`.env.example`** (без реальных значений)?

---

## 8. Связанные документы

- [`ENVIRONMENT_MAP.md`](ENVIRONMENT_MAP.md) — пути и symlink.
- [`RUNTIME_SOURCE_OF_TRUTH.md`](RUNTIME_SOURCE_OF_TRUTH.md) — фактический prod runtime.
- [`DEVELOPMENT_SAFETY_RULES.md`](DEVELOPMENT_SAFETY_RULES.md) — что нельзя ломать при разработке фронта.

---

*Справочный документ; файлы окружения и секреты в репозитории не изменяет.*
