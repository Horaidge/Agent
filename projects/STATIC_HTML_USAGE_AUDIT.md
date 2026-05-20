# Static HTML usage audit

Дата: 2026-05-07. Цель: найти ссылки на «свободные» HTML (`live_*.html`, `lite_*.html`, `dev_*.html`) и отделить их от production HTML/Jinja в backend.

Метод: поиск по репозиторию `/home/david` (glob + grep по именам и шаблонам).

**Обновление (2026-05-07):** перечисленные ниже корневые HTML и связанные стендалы **перенесены** в [`/home/david/playgrounds/html/`](/home/david/playgrounds/html/) — пути в таблицах ниже указаны как **логические имена файлов** (см. также [`playgrounds/README.md`](/home/david/playgrounds/README.md)).

---

## 1. Файлы в `playgrounds/html/` (ранее в корне `/home/david`), совпадающие с паттернами

### `live_*.html`

| Файл |
|------|
| `live_lkm_fix.html` |
| `live_workers_button.html` |
| `live_final_check.html` |
| `live_one_button.html` |
| `live_page_full.html` |
| `live_check_rev.html` |
| `live_content_path.html` |
| `live_dev_path.html` |

### `lite_*.html`

| Файл |
|------|
| `lite_tab_final.html` |
| `lite_tab_scaffold.html` |

### `dev_*.html`

Также в `playgrounds/html/`: `run_detail2.html`, `run_detail_smoke.html`, `workers_simple.html`, `workers_tab2.html`, `workers_tab_new.html` — тот же класс стендалов.

| Файл |
|------|
| `dev_index_workers2.html` |
| `dev_index_new.html` |

---

## 2. Ссылки в nginx

Проверены [`/home/david/nginx/nginx.conf`](/home/david/nginx/nginx.conf) и [`/home/david/nginx/nginx.projects.conf`](/home/david/nginx/nginx.projects.conf).

- **Прямых ссылок** на имена файлов `live_*.html` / `lite_*.html` / `dev_*.html` **нет**.
- Мarshруты проксируют на **FastAPI/Next**, а не на статические html из `$HOME`.

---

## 3. Ссылки в FastAPI (`projects/content`)

- По grep **имён файлов из корня** (`live_one_button`, `live_content_path`, и т.д.) — **совпадений в `.py` нет**.
- Есть обширная подсистема **Dream Pipeline Lite** с шаблонами вида `dream_pipeline_lite_*.html` в [`projects/content/ui/dev/templates/`](/home/david/projects/content/ui/dev/templates/) и роутами в [`projects/content/ui/dev/router.py`](/home/david/projects/content/ui/dev/router.py). Это **не** те же файлы, что `lite_tab_*.html` в `playgrounds/html/` — это **production/dev-console** артефакты приложения.

**Важно:** совпадение слова «lite» в именах **не** означает, что `lite_tab_*.html` в playgrounds подключены к роутеру.

---

## 4. Скрипты

- В обнаруженных shell-скриптах (`dev-refresh-content.sh`, `dev-restart-content.sh`, `run_dev.sh`) **ссылок на перечисленные HTML** нет.

---

## 5. Связь `dev_index_*.html` с приложением

В **`dev_index_new.html`** и **`dev_index_workers2.html`** встречается строка вида:

`hx-get="/dev/partials/dream/pipeline_lite_tab"`

Тот же паттерн есть в canonical шаблоне [**`projects/content/ui/dev/templates/index.html`**](/home/david/projects/content/ui/dev/templates/index.html).

**Интерпретация:** корневые `dev_index_*.html` выглядят как **копии/варианты playground** для HTMX-вызовов dev-консоли, открываемые **вручную** из файловой системы или через статический сервер, **не** как официальный отдаваемый FastAPI документ по умолчанию (официальная точка входа dev UI — маршруты `/dev` приложения).

---

## 6. Итоговая классификация

### Корневые `live_*.html`, `lite_*.html`

| Вердикт |
|---------|
| В коде/nginx **не найдено** импортов по имени. |
| **Похоже на локальные прототипы/стендалы** (проверка путей, кнопок, workers). |
| **Не трогать без явного решения:** могут быть закладками у оператора; удаление не требуется для работы compose-стека. |
| **Безопасно архивировать позже** только после подтверждения командой и бэкапом — **не в рамках этого аудита**. |

### Корневые `dev_*.html`

| Вердикт |
|---------|
| Дублируют фрагменты контракта с `/dev/...` API. |
| **Прототипы / offline playground.** |
| Реальный dev UI — **серверные шаблоны** под `projects/content/ui/dev/templates/`. |

### Шаблоны `dream_pipeline_lite_*.html`, `index.html` в `ui/dev/templates`

| Вердикт |
|---------|
| **Используются** приложением через `router.py`. |
| **Нельзя** удалять/перемещать без рефакторинга роутов. |

---

## 7. Рекомендации (без действий)

1. Зафиксировать владельца корневых HTML (человек/задача), затем при уборке — перенос в `archive/` или `experiments/` **отдельным PR с поиском по репо**.
2. Любая уборка должна повторить grep по полному пути и по содержимому (`hx-get`, `iframe`, `live_`).
3. Не путать **`lite_tab_*.html` в home** с **dream_pipeline lite** в репозитории content.

---

*Конец документа.*
