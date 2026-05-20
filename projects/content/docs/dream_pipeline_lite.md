# Dream Pipeline Lite — логика пайплайна и привязка к коду

Документ описывает **фактическое** поведение кода в `projects/content`, без смешения с «чат-моделью рисует кадры». Картинки на шаге 3 делает **image API (OpenRouter)** по текстовым полям карточки; чат LLM используется на шагах 1, **2a+2b**, 4.

---

## Участники

| Этап | Кто вызывается | Файл / функция |
|------|----------------|----------------|
| Шаг 1 | Chat LLM (`lite_chat_text`) | `dream_pipeline_lite.py`: `lite_environments_*`, `split_lite_step1_world` |
| Шаг 2a | Chat LLM | `lite_frames_*`, `split_lite_frame_cards`, `enrich_lite_frame_cards` |
| Шаг 2b | Chat LLM (JSON) | `lite_frames_prev_link_*`, `parse_lite_frames_prev_link_response`, `lite_apply_prev_link_classifier_raw`, обёртка `lite_run_step2_frames_with_prev_link` |
| Шаг 3 | **Image API** `tool_generate_image_openrouter` | `run_lite_visual_generation_chain` |
| Шаг 4 | Chat LLM (JSON плана) | `lite_compute_transition_plan`, `parse_lite_transition_plan_from_model_text` |
| Видео | **Не LLM**: `tool_image_to_video` + poll + ffmpeg | `run_lite_i2v_concat_to_mp4`, `lite_collect_animate_i2v_segments` |

Промпты markdown: `prompts/dream_pipeline_lite_environments.md`, `dream_pipeline_lite_frames.md`, **`dream_pipeline_lite_frames_prev_link.md`**, `dream_pipeline_lite_transitions.md`.

---

## Шаг 2a → структура кадра (текст)

Ответ модели режется на карточки `### Кадр N`. Тело карточки разбирается **`parse_frame_body_fields`**: поля `Опора`, `Изменение`, `Кадр`, `base_reference`, `character_references`, опционально устаревшее `use_previous_frame` в markdown (в промпте 2a поле **не просим** — см. файл промпта).

Дальше **`enrich_lite_frame_cards`**: нормализует строки, списки персонажей, вызывает **`lite_resolve_use_previous_frame`** с накопленным **`prior_for_chain`**. До шага 2b в карточке чаще всего **нет** явного `use_previous_frame` → намерение prev **false**, цепочка в enrich не «ломает» ничего критичного.

---

## Шаг 2b → `use_previous_frame` по JSON

Второй вызов чата: system из **`read_dream_pipeline_lite_frames_prev_link_raw`**, user — сон, шаг 1, **сырая markdown-раскадровка 2a** (`lite_frames_prev_link_user_message`).

Парсинг: **`parse_lite_frames_prev_link_response`** — ожидает JSON с **`use_previous_frame_by_index`** длины N (число кадров) или эквивалентный `frames[]` с индексами. Ошибка парсинга → исключение (шаг 2 в dev UI / воркер должен обработать).

**`lite_apply_prev_link_classifier_raw`** записывает в каждую карточку **`use_previous_frame: bool`** и вызывает **`lite_reapply_prev_chain_on_cards`**, который заново считает **`use_previous_frame_resolved`**, **`forced_prev_chain_break`** и UI-поля.

Сырой ответ 2b в персистентном run хранится в Mongo как **`step2_prev_link_raw`** (рядом с **`step2_raw`**).

---

## `use_previous_frame` / prev в image API — правила кода

**Намерение** после полного шага 2 задаёт **классификатор 2b** (`use_previous_frame` на карточке). Дальше **`lite_effective_use_previous_frame`** и **`lite_resolve_use_previous_frame`** (scene-aware continuity без hard-limit длины цепочки).

1. **Кадр с индексом 0** — предыдущего кадра нет, prev **никогда** не используется.
2. **Кадр i ≥ 1** — если модель 2b запросила prev (`true`) и нет scene-разрыва, в image API используется предыдущий кадр.
3. Поле **`forced_prev_chain_break`** сохранено для совместимости со старыми запусками, но в текущей политике технический лимит длины цепочки не применяется.

Сбор URL референсов: **`collect_lite_frame_reference_urls`** — при включённом prev (`use_previous_for_refs`, есть URL предыдущего кадра или режим превью-плана) в multipart уходит **только** изображение предыдущего кадра (`chain_prev_only`), без пластины окружения и без листов персонажей. Id в **`character_references`** нормализуются (`_normalize_lite_character_id_token`: убрать `**`, скобки `[id]`), чтобы `dreamer` и `** [dreamer]` не давали два одинаковых URL.

Текст в image API — только **`build_lite_frame_image_prompt(kad, izm)`**: поля раскадровки **«Кадр»** и **«Изменение»** (без отдельных дисклеймеров). Состав референсов (картинки) совпадает с **`collect_lite_frame_reference_urls`** / слотами; в UI показывается **`lite_refs_summary_for_ui`**, в текст запроса референсы не дублируются.

В dev UI шаг **3a** по умолчанию после пластин строит только **`lite_frame_generation_plans`** (без image API для кадров; prev в слоте **0** «ожидается» при плане). Параметр формы **`eager_frames=1`** — сразу **`run_lite_frame_visual_chain`**.

---

## Шаг 3 — что уходит в image API

Для каждого кадра **один** вызов **`tool_generate_image_openrouter(prompt, reference_image_urls=...)`**.

Карточки для шага 3 снова собираются из **того же markdown 2a** (`frames_text`) плюс **`lite_frame_cards_for_visual_from_text`**: если передан **`frames_prev_link_raw`** (сырой JSON ответа 2b), вызывается **`lite_apply_prev_link_classifier_raw`** — те же флаги prev, что после шага 2. В dev UI поле **`#dream-lite-frames-prev-link-store`** обновляется OOB вместе с раскадровкой; без него шаг 3 видит только 2a и ведёт себя как «везде без prev». Полный пайплайн в одном запросе передаёт prev из памяти сервера.

- **Не** «отбрасывается модель чата» — чат тут не вызывается; уходит **собранный строкой** `img_prompt` + список URL/data URI референсов (окружение, листы персонажей, опционально предыдущий кадр).
- **`character_references`** перед сбором URL **дедуплицируются** (и в enrich), чтобы один и тот же id не дал два одинаковых листа в multipart.

- Если кадры визуально похожи при отсутствии prev — чаще вина **image-модели** или **одинаковые тексты** шага 2a, либо классификатор 2b не выставил **`true`**, когда нужна непрерывность, либо **не был передан** `frames_prev_link_raw` на шаг 3.

---

## Шаг 4 и видео

- Шаг 4 получает **только текстовые** метаданные кадров (+ флаги `use_previous_frame_resolved`, `forced_prev_chain_break`) — см. **`lite_transitions_user_payload_dict`** (картинки в контекст не кладутся).
- **`animate_transition`** между i и i+1 → сегмент i2v с **`image_url`** кадра i и **`last_frame_url`** кадра i+1 (если оба успешны).
- Только **`hard_cut`** → отдельного i2v на эту пару нет; итоговый mp4 — склейка клипов по порядку.

---

## Персистентный run (Telegram / API)

**`dream_lite_run_worker.process_dream_lite_run_step`** и коллекция **`dream_lite_runs`** — та же логика полей и **`lite_resolve_use_previous_frame`**, но по одному шагу за вызов. Фаза **`text_step2`** выполняет **`lite_run_step2_frames_with_prev_link`** и пишет **`step2_raw`**, **`step2_prev_link_raw`**, **`frame_cards`**.

---

## Если классификатор 2b ответил с ошибкой

Парсер не извлёк валидный JSON или длина массива не совпала с числом кадров → шаг 2 падает целиком; правится **промптом / моделью** или контрактом JSON в `dream_pipeline_lite_frames_prev_link.md`.
