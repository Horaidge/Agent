# Workspace `/home/david`

| Путь | Содержимое |
|------|------------|
| [`projects/`](projects/) | Код: **`content`**, **`agent/app`**, **`agent-next`**; env: [`ENVIRONMENT_MAP.md`](projects/ENVIRONMENT_MAP.md), [`ENVIRONMENT_STRATEGY.md`](projects/ENVIRONMENT_STRATEGY.md). |
| [`docs/`](docs/) | Вспомогательные README (LLM, VAPI, структура). |
| [`playgrounds/`](playgrounds/) | HTML-прототипы и архивы; **не** production. |
| [`projects/agent-next/`](projects/agent-next/) | Изолированный Next.js для локального voice (VAPI), dev **3100**. |
| [`nginx/`](nginx/) | Примеры/запасные конфиги; фактический vhost прод-сервера — см. `projects/RUNTIME_SOURCE_OF_TRUTH.md`. |
| `docker-compose*.yml` | Описание контейнеров; активный стек — в документе **Runtime Source of Truth**. |
| `dev-*.sh` | Скрипты локального dev для `projects/content`. |
