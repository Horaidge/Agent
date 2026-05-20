# Docker Runtime Snapshot

**Момент съёмки:** 2026-05-07 (команды только чтения: `docker ps`, `inspect`, `network ls`, `volume ls`). Runtime **не изменялся**.

---

## 1. `docker ps -a` (краткая таблица)

| NAMES | IMAGE | STATUS (на снимке) | PORTS |
|-------|--------|-------------------|--------|
| `david_content_1` | `david_content` | Up | `8000/tcp`, `127.0.0.1:8002->8002/tcp` |
| `david_mongo_1` | `mongo:7` | Up | `27017/tcp` (без publish на хост) |
| `david_agent_1` | `david_agent` | Up | `127.0.0.1:3001->3000/tcp` |

Других контейнеров в выводе **не было** (в т.ч. **нет** контейнера `nginx` из compose).

---

## 2. Docker networks

| NAME | DRIVER |
|------|--------|
| `bridge` | bridge |
| **`david_default`** | bridge ← сеть проекта `david` |
| `host` | host |
| `none` | null |

---

## 3. Docker volumes (фрагмент списка)

Присутствуют тома в т.ч.:

- **`david_content_mongo_data`** — используется контейнером **`david_mongo_1`** для `/data/db`.
- **`david_mongo_standalone_data`**, **`mongo_standalone_data`** — присутствуют в системе; на момент снимка отдельный контейнер `infra_mongo` **не был** в `docker ps` (возможен остановленный/альтернативный профиль).

Старые анонимные/прочие тома в выводе `docker volume ls` не детализировались — при уборке диска нужен отдельный audit с `docker volume inspect`.

**Mount у `david_mongo_1` (подтверждено):**

- Тип `volume`, имя **`david_content_mongo_data`** → `/data/db`
- Дополнительный том для `configdb` (hash-имя) — стандартно для Mongo.

---

## 4. Compose project metadata (из labels контейнеров)

| Поле | Значение |
|------|----------|
| `com.docker.compose.project` | `david` |
| `com.docker.compose.project.config_files` | `/home/david/docker-compose.projects.yml` (или относительный путь от cwd) |
| `com.docker.compose.project.working_dir` | `/home/david` |
| Сервисы | `content`, `agent`, `mongo` |

---

## 5. Заметки по инструментам

- Команда `docker compose` (v2 plugin) на хосте может быть **недоступна**; используется **`docker-compose`** 1.29.2.
- `docker-compose -f docker-compose.yml ps` для **корневого** [`docker-compose.yml`](/home/david/docker-compose.yml) на снимке показывал **пустой** набор сервисов — **этот стек не был активен**.

---

## 6. Ограничения снимка

- Не проводился `docker inspect` полного списка env в документ (чтобы не утекли секреты); для SoT см. [`RUNTIME_SOURCE_OF_TRUTH.md`](/home/david/projects/RUNTIME_SOURCE_OF_TRUTH.md).
- Состояние **могло измениться** после момента съёмки; перед операциями перезапустить команды read-only.

---

*Конец документа.*
