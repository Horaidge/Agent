# Development safety rules

Документ для команды и для AI-агентов: **границы при работе над procedural frontend (`agent-next`) и смежными задачами.**  
Дата: 2026-05-07.

---

## 1. Зона высокого риска (production runtime)

Следующие компоненты **не изменять** без отдельного согласования, code review и плана отката:

| Компонент | Почему |
|-----------|--------|
| [`/home/david/docker-compose.projects.yml`](/home/david/docker-compose.projects.yml) | Определяет образы **content** / **agent** / **mongo** |
| **System nginx** (`/etc/nginx/sites-enabled/voice`) | Единственный публичный ingress для домена и **Telegram webhook** |
| **`WEBHOOK_PATH`**, `TELEGRAM_WEBHOOK_URL`, токен бота | Ошибка = остановка Telegram |
| **`projects/content/.env`** на сервере | Секреты и runtime-поведение backend |
| **`projects/agent/config/.env`** | Сборка/ключи VAPI для текущего прод-фронта |
| **Имена/тома Mongo** (`david_content_mongo_data`) | Потеря/порча данных |

---

## 2. Явно запрещённые действия в рамках «safe frontend iteration»

- **Rebuild / redeploy** контейнеров `david_content_1`, `david_agent_1`, `david_mongo_1` без approval.
- **`docker compose up/down`** на production host без окна работ.
- Изменение **путей webhook** или заголовков прокси для `/telegram/`.
- Перенос или удаление **`projects/agent/app`**, **`projects/content`**, монтированных томов.
- Публикация **Mongo 27017** на `0.0.0.0`.
- Использование **production** `.env` или ключей API в репозитории `agent-next`.
- Подключение experimental frontend к **production Mongo** «для удобства».

---

## 3. Разрешённые и безопасные действия

- Создание и редактирование только внутри **`/home/david/projects/agent-next`** (когда каталог будет создан).
- Локальный **`pnpm dev`** на порту из [`PORT_ALLOCATION_MAP.md`](/home/david/projects/PORT_ALLOCATION_MAP.md).
- Документация, диаграммы, audit markdown в `projects/`.
- Локальные git-ветки, не затрагивающие production compose на сервере.

---

## 4. Safe workflow (экспериментальный frontend)

1. Убедиться, что команда работает в **`agent-next`**, а не в `agent/app`.
2. Создать **новый** `.env.local`; не копировать секреты с прод-сервера.
3. Перед `pnpm dev`: проверить свободный порт (`ss -tlnp`).
4. Интеграции с backend — только через **явно названный** модуль-адаптер; по умолчанию **моки**.
5. Любое изменение, затрагивающее `content` / nginx / compose — **стоп** и вынести в отдельную задачу.

---

## 5. Контрольный чеклист перед merge в «инфраструктурные» файлы

Если PR трогает что-то из списка — **не merge без** infra owner:

- `docker-compose*.yml`
- `**/nginx/**` или `/etc/nginx/**`
- `projects/content/application.py`, `bot/webhook.py`, `core/config/settings.py`
- GitHub Actions / CI, деплой-скрипты на сервере

---

## 6. Инцидент: «сломали webhook»

Не править вслепую; проверить по порядку:

1. [`RUNTIME_SOURCE_OF_TRUTH.md`](/home/david/projects/RUNTIME_SOURCE_OF_TRUTH.md) — актуальный ли vhost и путь `/telegram/`.
2. Логи `david_content_1` и ответ Bot API на `getWebhookInfo`.
3. Согласованность `WEBHOOK_PATH` и nginx `location` (без публикации секретов в тикетах).

---

*Конец документа.*
