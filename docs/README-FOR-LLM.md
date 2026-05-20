# README FOR LLM

Этот документ описывает структуру и рабочую архитектуру проекта в `/home/david`.

## Корневая структура

- `projects/content` — основной backend (FastAPI + Telegram + LLM + Dream pipeline + Dev UI).
- `projects/agent/app` — frontend на Next.js (VAPI).
- `projects/agent/config` — конфиги/env для frontend.
- `docker-compose.mongo.yml` — отдельный запуск MongoDB.
- `dev-refresh-content.sh` — корневой скрипт перезапуска backend dev-режима + Cloudflare tunnel.

## Основной backend: `projects/content`

### Назначение

Сервис для Telegram-бота и внутренних инструментов:

- webhook-прием сообщений;
- оркестрация LLM-ответов и tool-calls;
- Dream pipeline (сон -> сцены -> изображения -> анимация -> финальное видео);
- dev-консоль `/dev` и Gradio `/ui`.

### Ключевые директории

- `application.py` — сборка FastAPI приложения и DI зависимостей.
- `main.py` — точка запуска uvicorn.
- `bot/` — webhook, роутеры, middleware, Telegram handlers.
- Чат-агент (`services/chat/chat_orchestrator.py`): tools по умолчанию включают **`generate_image`**, **`image_to_video`**, **`concat_video_clips`** (склейка готовых mp4 по URL через ffmpeg → `ui/dev/static/chat_concat/`), **`generate_dream_pipeline`**. Инструкции для модели по сценарию картинка→видео→склейка: **`prompts/chat_video_scenario_tools.md`** (подмешиваются в system после `system_prompt.md`).
- `services/`
  - `chat/` — чат-оркестратор и история;
  - `dreams/` — dream pipeline и planner;
  - `tools/` — tool definitions, схемы и исполнители;
  - `llm/` — OpenAI обертки.
- `ui/`
  - `dev/` — dev-консоль (Jinja + HTMX);
  - `gradio_app.py` — UI `/ui`.
- `storage/` — репозитории Mongo (chat, tool calls, dream runs/scenes/frames/videos и т.д.).
- `prompts/` — `system_prompt.md`, `global_model_policy.md`, `dream_beat_planner.md` (0A), `dream_decomposition.md` (Сценарист 0B), `dream_scene_motion_decompose.md` (production: сцены+motion), `dream_image_prompts.md`, …
- `data/runtime/` — runtime-артефакты (в т.ч. tunnel URL/pid для dev).

## Dev UI: Agent Control (в `/dev`)

Вкладка Agent Control объединяет:

- `Prompt`
- `Tools`
- `Pipelines`
- `Live`
- `Analytics`

### Tool Registry

Инструменты разделены по типам:

- `atomic`
- `async_atomic`
- `pipeline`

Для atomic tools доступен playground:

- ручной JSON input;
- запуск tool;
- просмотр raw request/response, status, error, latency.

### Pipeline Inspector

Показывает pipeline как процесс, а не как обычную карточку:

- Entry/Trigger;
- user context;
- flow/stages;
- child tool calls;
- queue/live state;
- storage artifacts.

## Pipeline (Dream) — технически

End-to-end цепочка живёт в `projects/content/services/dreams/`. Точка входа для пользователя — intent «сон» в Telegram и вызов `DreamPipelineService` (создание `dream_runs`, затем исполнение стадий).

### Где что лежит

| Компонент | Файл / модуль |
|-----------|----------------|
| Оркестратор стадий, контекст пользователя, генерация кадров | `services/dreams/dream_orchestrator.py` (`DreamPipelineService`, `resolve_image_reference`) |
| Три LLM-шага планирования (сцены → картинки → анимация) | `services/dreams/dream_scene_planner.py` |
| Модели данных и константы стадий | `services/dreams/models.py` |
| «Ворота» лица / базового персонажа | `services/dreams/character_gate.py` |
| System для production `decompose_dream_scenes` (сцены + motion) | `prompts/dream_scene_motion_decompose.md` + fallback `SYSTEM_DECOMPOSE` в `dream_scene_planner.py` |
| System для Сценариста (0B, dev) | `prompts/dream_decomposition.md` |
| System для Beat Planner (0A, dev) | `prompts/dream_beat_planner.md` + fallback `SYSTEM_BEAT_PLANNER` |
| Подмешивание `global_model_policy` ко всем system | `services/llm/openai_chat_service.py` → `merge_with_global_model_policy` |
| Редактирование промптов planning layer в dev | mini lab 0A → `POST /dev/api/prompts/dream-beat-planner-md`; 0B → `POST /dev/api/prompts/dream-decomposition-md`; Agent Control → отдельные карточки файлов |
| Верхняя граница числа сцен (шаг 1) | `MAX_DECOMPOSE_SCENES` в `dream_scene_planner.py` (плейсхолдер `{max_scenes}` в markdown); фактическое **N** сцен задаёт модель, от 1 до этого лимита |

### Поток выполнения (упрощённо)

`_execute_pipeline` последовательно вызывает:

1. **`_stage_1_decompose`** — три JSON-вызова к OpenAI:
   - `decompose_dream_scenes` — сон → список `DreamSceneOutline` (system из `_decompose_system_prompt()` / файл `dream_scene_motion_decompose.md`);
   - `build_visual_prompts_for_scenes` — визуальные промпты и `reference_type` на сцену;
   - `build_animation_prompts_for_scenes` — промпты анимации и длительность;
   - затем `merge_scene_plan` склеивает всё в `DreamScenePlan`, сцены пишутся в `dream_scenes`.
2. **`_stage_2_generate_images`** — для каждой сцены `resolve_image_reference(ctx, dream_repo, scene)` выбирает эталон (база / лицо / окружение / none). При наличии URL эталона вызывается **`tool_edit_image`** (консистентность лица), иначе **`tool_generate_image`**. Кадры журналируются в `generated_frames` / `generated_images`.
3. **`_stage_3_animate`** — image-to-video по кадрам (`video_jobs`, `scene_videos`).
4. **`_stage_4_assemble`** — сборка финального ролика (`story_videos`).

### Planning Layer JSON контракты (Bit Planner → Сценарист → Режиссёр)

Ниже — рабочая структура JSON для planning-цепочки в dev sandbox (`/dev`, вкладка Dream Pipeline mini lab).

#### 0A · Bit Planner

**Input (к модели, логический контракт):**

```json
{
  "dream_text": "string",
  "asset_context": {
    "has_face": true,
    "has_base_character": true,
    "secondary_actors": [
      { "actor_name": "string", "asset_id": "string" }
    ],
    "missing": ["string"],
    "environment_hints": [["environment", "asset_id"]]
  }
}
```

**Output (из Bit Planner):**

```json
{
  "header_context": {
    "summary": "string",
    "environment": { "world_summary": "string" },
    "entities": [
      { "env_id": "string", "title": "string", "description": "string" }
    ],
    "world_properties": ["string"],
    "meta": { "bits_total": 3 }
  },
  "beats": [
    {
      "beat_index": 1,
      "title": "string",
      "core_event": "string",
      "beat_description": "string",
      "event_steps": ["string"],
      "actors": ["string"],
      "environment_refs": ["env_id"],
      "environment_focus": "string",
      "main_character_state": "string",
      "key_objects_or_entities": ["string"],
      "transition_out": "string",
      "story_function": "setup|escalation|transition|danger|discovery|climax|resolution"
    }
  ]
}
```

#### 0B · Сценарист

**Input (из Bit Planner):**

```json
{
  "header_context": { "...": "без изменений от Bit Planner" },
  "beats": [{ "...": "beat item" }]
}
```

**Output (из Сценариста):**

```json
{
  "header_context": { "...": "без изменений, просто passthrough" },
  "scenes": [
    {
      "scene_index": 1,
      "source_beat_index": 1,
      "title": "string",
      "short_description": "string",
      "scene_description": "string",
      "actors": ["string"],
      "environment": "string",
      "mood": "string",
      "scene_goal": "string",
      "main_character_state": "string",
      "key_objects_or_entities": ["string"]
    }
  ]
}
```

#### 1 · Режиссёр

**Input (из Сценариста):**

```json
{
  "header_context": { "...": "тот же объект" },
  "scenes": [{ "...": "scene item" }]
}
```

**Output (из Режиссёра):**

```json
{
  "header_context": { "...": "тот же объект" },
  "final_scenes": [
    {
      "scene_index": 1,
      "source_beat_index": 1,
      "title": "string",
      "visual_prompt": "string",
      "image_prompt": "string",
      "reference_type": "base_character|selected_character|environment|none"
    }
  ]
}
```

**Важно по цепочке:**

- `header_context` — единый и неизменяемый слой контекста мира.
- Ручной выбор отдельных сцен для режиссёра не нужен: режим `per_scene` проходит все сцены последовательно.
- В `per_scene` на каждом шаге в модель снова передаётся тот же `header_context`.

### Сколько вызовов: языковая модель (OpenAI), картинки (Qwen), видео (Wan)

Пусть **N** — число сцен в итоговом плане (столько же кадров и столько же коротких видео по сценам).

| Тип | Сколько раз (типичный успешный run) | Где в коде |
|-----|-------------------------------------|------------|
| **Языковая модель (OpenAI, `json_completion`)** | **до 5** на один полный запуск из Telegram при настроенном API | См. ниже по строкам |
| **Генерация изображений (Qwen Image)** | **N** (по одному успешному запросу на сцену; при ошибке до **2** попыток на сцену) | `_stage_2_generate_images` → `tool_edit_image` или `tool_generate_image` |
| **Генерация видео (Wan / image-to-video)** | **N** (по одному `video_job` на сцену) | `_stage_3_animate` → `VideoJobService.create_video_job` |

**Детализация вызовов OpenAI** (все — отдельные HTTP-запросы `chat.completions`, не один «батч»):

1. **Интент** — `_detect_intent`: 1 вызов, когда пользователь прислал текст и нужно отличить `dream` от `chat` (если API не настроен, эвристика **без** LLM).
2. **Актёры** — `_extract_actor_names`: 1 вызов перед стартом декомпозиции (после того как есть лицо/база), чтобы получить список второстепенных персонажей (если API не настроен — пустой список **без** LLM).
3. **Планирование сна** — `_stage_1_decompose`: ровно **3** вызова подряд — декомпозиция сцен → промпты картинок → промпты анимации (`dream_scene_planner.py`).

Итого при полном пути и работающем OpenAI: **1 + 1 + 3 = 5** вызовов языковой модели на один run.

**Уточнение:** вызов классификатора интента (`_detect_intent`) делается только когда сон запускается из **Telegram** через `detect_intent_and_maybe_start`. При **`run_from_dev`** и при запуске из **tool-call** без этого шага первого LLM нет — остаётся **1 + 3 = 4** вызова (актеры + три шага планирования), если не считать отдельные ветки `awaiting_character` / стиль.

**Склейка финала (stage 4):** локальный **ffmpeg**, отдельных вызовов к облачным моделям нет.

### После разметки: зачем поля сцены и что реально уходит в модели

**Про «отправку сообщений».** После декомпозиции пользователю в Telegram уходят только **короткие статусные реплики** оркестратора («сон разобран…», «генерирую изображения…» и т.д.). Отдельно **не рассылаются** `short_description`, `mood` и т.п. как сообщения — это поля **плана** (Mongo, dev UI, входы для следующих LLM-шагов и для сборки промпта картинки).

**Две вещи — мало.** В Qwen на генерацию кадра уходит **не** только «текст сцены + референс». Референс — отдельно (`tool_edit_image` / `tool_generate_image`). Текстовая часть — это **`visual_prompt`** (шаг 2 LLM), к которой в коде **дописываются** суффикс персонажа/стиля, строки про второстепенных актёров, при необходимости **`environment_requirement`** (`Setting: …`) и **`mood`** (`Mood: …`). То есть `scene_description` / `short_description` напрямую в image model не обязаны уходить целиком — они кормят **шаги 2–3 LLM** и **fallback** в `merge_scene_plan`, если модель пропустила `visual_prompt` / `animation_prompt`.

| Поле | Назначение в текущем коде |
|------|---------------------------|
| `scene_description` | Смысл сцены для LLM (шаги 2–3), fallback для `visual_prompt` / анимации в `merge_scene_plan`. |
| `short_description` | Краткий текст для UI/логов; если пусто — подставляется из `scene_description` при декомпозиции. |
| `character_requirement` | Логика **`resolve_image_reference`**: значение `none` помечает кадр «без людей» — не навязываем эталон лица; иначе приоритет база/лицо. Также в контексте для LLM. |
| `environment_requirement` | Ветка «окружение» в `resolve_image_reference` (если есть env-ассеты и непустое поле); плюс строка `Setting: …` в финальном промпте картинки. |
| `mood` | Добавляется в финальный промпт картинки как `Mood: …`; задаёт тон кадра вместе с визуальным описанием. |
| `duration_sec` | Длительность клипа анимации (шаг 3), клампится в допустимый диапазон. |
| `camera_motion` | **Сейчас не используется** ни при генерации изображения, ни при вызове video API — только хранится в модели/JSON после шага 1. Резерв под будущую логику или ручной промпт; на поведение пайплайна не влияет. |

Итог: разметка даёт **структурированный план** (кто в кадре, локация, настроение, длительность), из которого **шаг 2** делает кинематографичный `visual_prompt`, а оркестратор **склеивает** итоговую инструкцию для Qwen и отдельно подставляет **референс** из БД при наличии URL/data URI.

### Псевдокод вызова планировщика (шаг 1a)

Интерфейс не «одна функция для всего пайплайна», а явные async-функции планировщика; их вызывает оркестратор:

```python
# Уже внутри DreamPipelineService._stage_1_decompose — фрагмент идеи:
dream_summary, outlines = await decompose_dream_scenes(
    openai=self._openai,
    dream_text=dream_text,
    asset_context=ctx,  # has_face, has_base_character, secondary_actors, …
)
vp_map = await build_visual_prompts_for_scenes(
    openai=self._openai,
    dream_text=dream_text,
    dream_summary=dream_summary,
    outlines=outlines,
    asset_context=ctx,
)
ap_map = await build_animation_prompts_for_scenes(
    openai=self._openai,
    dream_text=dream_text,
    outlines=outlines,
    visual_prompts_by_index=vp_map,
    asset_context=ctx,
)
plan = merge_scene_plan(dream_summary, outlines, vp_map, ap_map)
```

Плейсхолдер `{max_scenes}` в markdown-промптах подставляется при загрузке, где поддерживается `.format` (см. `_decompose_system_prompt`, `_beat_planner_system_prompt`, `_scenarist_system_prompt` в `dream_scene_planner.py`).

### Состояния job/model

- `created`
- `running`
- `waiting_input`
- `generating_images`
- `animating`
- `assembling`
- `completed`
- `failed`

## Dream Pipeline Lite — Telegram, раскадровка и финальное видео

Подробная логика полей, prev и вызовов API: **`projects/content/docs/dream_pipeline_lite.md`**.

Это **отдельный** пайплайн от production Dream (`dream_runs` → `dream_scenes` → …). Он проще по продуктовой идее: **текст сна → ключевые кадры (storyboard) → картинки по кадрам → план монтажа (JSON) → image-to-video между выбранными парами кадров → склейка одного mp4**. Именно **Lite** задуман как основа сценария для **Telegram-бота** и внешних агентов, где нужна анимация между готовыми изображениями, а не полный planning layer 0A/0B/Режиссёр.

### Где в коде

| Компонент | Назначение |
|-----------|------------|
| `services/observability/dream_pipeline_lite.py` | Промпты шагов 1–2–4, разбор плана переходов, сборка ref-URL для кадров, `run_lite_visual_generation_chain` (картинки), `run_lite_i2v_concat_to_mp4` (очередь i2v + ffmpeg), materialize/resolve URL для Mongo |
| `services/observability/dream_lite_run_worker.py` | Пошаговый воркер Mongo-run: один вызов = одна атомарная операция (`process_dream_lite_run_step`) |
| `storage/dream_lite_run_repository.py` | Коллекция `dream_lite_runs`, создание/чтение/патч документа по `(user_id, lite_run_id)` |
| `services/dreams/dream_lite_telegram_runner.py` | Цикл шагов до `done` + отправка финального mp4 в чат |
| `bot/dream_lite_handlers.py` | Команды Telegram `/dreamlite` и `/lite` |
| `api/dream_lite_montage_json.py` | HTTP JSON без dev UI: `POST /api/dream/lite/montage/plan_json`, `POST /api/dream/lite/montage/render_json` |
| Промпты markdown | `prompts/dream_pipeline_lite_environments.md`, `dream_pipeline_lite_frames.md`, `dream_pipeline_lite_transitions.md`, `dream_pipeline_lite_transitions_seedance.md` (подгружаются через `system_prompt_loader`) |

### Сколько инференсов языковой модели (чат)

Каждый вызов `lite_chat_text` — **один** HTTP `chat.completions` (роль `system` + роль `user`), не «один инференс на весь сон».

На полный прогон Lite **минимум три отдельных LLM-запроса**:

1. **Шаг 1** — окружения и персонажи: в `user` уходит **только текст сна**; в `system` — правила шага 1.
2. **Шаг 2** — раскадровка: в `user` уходит **текст сна + полный сырой markdown шага 1**; в `system` — правила раскадровки.
3. **Шаг 4 (план монтажа)** — LLM может вернуть:
   - **плотный режим**: transitions по соседям `i -> i+1`,
   - **разрежённый режим**: `keyframes` + transitions по опорным парам (например `0->2->4->last`).
   
   В `user` уходит **одна строка с вложенным JSON** (`dream_text`, карточки окружений/персонажей, **компактные метаданные кадров**: `kad`, `izmenenie`, `base_reference`, **`use_previous_frame_resolved`**, **`forced_prev_chain_break`**, флаги успеха генерации и т.д.). **Сами пиксели кадров в промпт не вставляются** (ни data URI, ни длинные URL) — иначе контекст раздувается; модель опирается на **текстовое описание** ключей и флаги перехлёста, а изображения подставляются **в коде** при i2v по выбранным парам из плана.

   **Важно про новый Seedance-режим:** воркер выбирает preset через `lite_resolve_montage_preset(...)`:
   - если `video_policy.montage_preset == "seedance"` **или** `selected_video_model` содержит `seedance`, используется **отдельный** system prompt `transition_plan_seedance_system_prompt` (или fallback `prompts/dream_pipeline_lite_transitions_seedance.md`);
   - иначе используется `transition_plan_system_prompt` (или fallback `prompts/dream_pipeline_lite_transitions.md`).

   В оба режима дополнительно подмешиваются runtime-хинты `prompt_mode` и `audio_required` через `lite_build_transition_system_prompt(...)`.
   В Seedance-ветке для `animate_transition` ожидается `segment_mode` (`pairwise` / `single_anchor`); в общем режиме это поле может не прийти и нормализуется сервером.

Дальше **не чат**, а отдельные вызовы: **по одному запросу на картинку** (окружения, персонажи, каждый кадр) через image API, затем **по одному video job** на каждый сегмент `animate_transition`, затем **локальный ffmpeg** при склейке.

### Перехлёст кадров (`use_previous_frame`) и смысл для монтажа

**Превью (prev в image API)** включается **только если шаг 2 явно задал `use_previous_frame: true`** (или да/true в разметке). Если поля нет — считается **false**, в запрос картинки уходят окружение + персонажи, без предыдущего кадра. Фактическое решение после лимита — **`use_previous_frame_resolved`**; принудительный обрыв — **`forced_prev_chain_break`**.

- **Лимит цепочки:** не более **`LITE_MAX_PREV_CHAIN_LINKS = 3`** подряд кадров с **фактическим** prev (`lite_resolve_use_previous_frame` в `dream_pipeline_lite.py`). На следующем «хотел true» код сбрасывает цепочку.
- **Смысловая интерпретация (важно для модели плана монтажа и для разработчиков):** последовательность кадров, где каждый следующий **перехлёстывается** с предыдущим, описывает **одну непрерывную визуальную нить** (один «поток» сцены, эволюция одного состояния). Это **не** отдельные несвязные статичные миры, а **цепочка одного монтажного замысла** до следующего жёсткого разрыва или смены опоры.
- **Связь с типами переходов в JSON плана:** в плотном режиме между соседними индексами `i → i+1` модель выбирает **`animate_transition`** или **`hard_cut`**. В разрежённом режиме модель может выбрать только опорные `animate_transition` (не-смежные пары), а `hard_cut` использовать как явные границы при необходимости.
- На границах **цепочек перехлёста** и после **`forced_prev_chain_break`** обычно ожидается `hard_cut`, если смысл скачет; внутри непрерывной цепочки чаще уместен `animate_transition`.
- Технически i2v вызывается по тем парам, которые пришли в `transition_plan.transitions` как `animate_transition` и имеют валидные URL (для `single_anchor` допускается отсутствие `last_frame_url` в режиме `first_last_frame`).

### Последний этап: что должно быть для создания видео

Финальная стадия **не** делегируется чат-модели как tool-call. После того как есть:

- **`generated_frames`** (или эквивалент): у каждого кадра — успешная генерация и URL/путь к изображению (после Mongo часто короткий `/dev/static/dream_lite_runs/...`, перед i2v поднимается до формата, который ест video backend);
- **`transition_plan`** с массивом **`transitions`**, при необходимости **`scenes`**, и служебным `montage_mode` (`dense`, `sparse`, `dense_fallback`, `hard_cut_fallback`),

код:

1. Собирает список сегментов **`lite_collect_animate_i2v_segments`**: только пары с `transition_type == "animate_transition"`, для каждой пары — **стартовый кадр** (`image_url`) и при необходимости **конечный кадр** (`last_frame_url`), плюс **`motion_prompt`** и `segment_mode`.
   - Для Seedance `segment_mode=single_anchor` считается валидным даже без `last_frame_url` в режиме `first_last_frame`.
   - Для обычного `pairwise` в `first_last_frame` нужны оба кадра.
2. Для каждого сегмента вызывает **`tool_image_to_video`** (async job), опрашивает **`video_jobs`** до успеха/ошибки.
3. Склеивает полученные mp4 через **`assemble_remote_mp4s`** (ffmpeg) в файл под **`ui/dev/static/dream_lite_final/`** и выставляет публичный путь вида **`/dev/static/dream_lite_final/<имя>.mp4`**.

Если парсинг ответа LLM сломан, применяется безопасный fallback-план (`dense_fallback`) с animate-парами по соседям, чтобы пайплайн i2v не обрывался из-за одного невалидного JSON.

Параметры `reference_frame_stride` / `scene_segment_stride` считаются legacy: при `montage_mode == "sparse"` они принудительно игнорируются (ставятся в 1), чтобы не конфликтовать с решением LLM.

Персистентный путь (Telegram): команды **`/dreamlite`** / **`lite`** + текст сна — создаётся документ в **`dream_lite_runs`**, затем в цикле вызывается **`process_dream_lite_run_step`** до фазы **`completed`** и заполнения **`final_video_url`**. Stateless dev: **`POST /dev/api/dream/lite/pipeline_all_steps`** (HTMX) или раздельно JSON **`plan_json`** + **`render_json`**.

### Состояние Mongo-run (кратко)

Документ в **`dream_lite_runs`** хранит фазу **`step_phase`** (`text_step1` → … → `transition_plan` → `anim_i2v` → `finalize_clips` → `completed`), сырые ответы LLM, карточки, слоты генерации, **`transition_plan`**, клипы **`generated_anim_clips`**, **`final_video_url`**, **`final_assembly_error`**. Подробная схема полей — в `DreamLiteRunRepository.create_run`.

## MongoDB и хранение данных

MongoDB используется как отдельный сервис (обычно через Docker).  
В приложении доступ к БД идёт через репозитории в `projects/content/storage/*`.

Важно: история сообщений и профиль пользователя НЕ лежат в одной коллекции — модель хранения нормализована по сущностям.

### База и коллекции (основные)

- `inbound_messages` — входящие Telegram-сообщения (сырой поток).
- `conversation_messages` — история диалога для LLM-контекста.
- `model_calls` — логи запросов/ответов модели (для дебага).
- `tool_calls` — логи вызовов инструментов и результатов.
- `user_profiles` — профиль пользователя (`base_character_asset_id`, флаги ожидания и пр.).
- `dream_assets` — пользовательские визуальные ассеты (face / character / environment / other).
- `generated_images` — журнал сгенерированных изображений пользователя (включая кадры pipeline).
- `video_jobs` — async-задачи image-to-video.
- `dream_runs` — запуски Dream pipeline (статусы, текущая стадия, snapshot контекста).
- `dream_scenes` — сцены внутри run (план, промпты, метаданные).
- `generated_frames` — кадры сцен Dream pipeline.
- `scene_videos` — видео по отдельным сценам.
- `story_videos` — финальные собранные видео.
- `dream_lite_runs` — **Dream Pipeline Lite**: пошаговое состояние одного прогона (текст сна → кадры → план монтажа → i2v → mp4), ключ `(user_id, lite_run_id)`.
- `observability_events` — события observability для `/dev`.

### Связи между сущностями

- Пользователь: `user_id` / `telegram_user_id`.
- Диалог:
  - `inbound_messages` — raw вход;
  - `conversation_messages` — то, что идёт в контекст модели.
- Dream pipeline:
  - один `dream_runs` -> много `dream_scenes`;
  - один `dream_runs` -> много `generated_frames` -> много `scene_videos`;
  - один `dream_runs` -> один `story_videos` (финал).
- Визуальная идентичность:
  - `user_profiles.base_character_asset_id` указывает на `dream_assets._id`;
  - этот asset используется как reference для консистентности персонажа.

## Запуск в dev

Из корня:

```bash
./dev-refresh-content.sh
```

Скрипт:

- останавливает старый процесс на dev-порту;
- перезапускает Cloudflare quick tunnel;
- поднимает `projects/content/run_dev.sh`;
- обеспечивает актуальный webhook URL для Telegram.

## Важно для LLM-агентов

- Pipeline и Tools — разные сущности.
- `generate_dream_pipeline` должен интерпретироваться как workflow orchestration, а не как простой atomic tool.
- Для диагностики использовать `/dev` -> Agent Control:
  - Tools playground для точечных проверок;
  - Pipeline Inspector для end-to-end анализа выполнения.