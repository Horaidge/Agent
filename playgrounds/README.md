# Playgrounds (не production)

Статические **HTML-стендалы** и прочие одноразовые артефакты. Они **не** подключены к nginx и **не** отдаются FastAPI (см. [`projects/STATIC_HTML_USAGE_AUDIT.md`](../projects/STATIC_HTML_USAGE_AUDIT.md)).

## Содержимое

| Каталог | Назначение |
|---------|------------|
| [`html/`](html/) | Прототипы: `live_*`, `lite_*`, `dev_*`, `run_detail*`, `workers_*`. Открывайте локально или через статический сервер; пути к API внутри файлов рассчитаны на ваш стенд. |
| [`archives/`](archives/) | Произвольные архивы (например загрузки). |

Продакшен UI: **`projects/content/ui/dev/templates/`** и Next **`projects/agent/app`**.
