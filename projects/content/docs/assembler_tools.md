# Сборщик: инструменты исполнения

Режиссёр (planning layer) выдаёт только JSON: `header_context` + `final_scenes` — без вызова моделей.

Сборщик читает этот output и вызывает backend-tools.

## Генерация изображений — `generate_image_openrouter`

- Реализация: `services/images/openrouter_image_client.py`, `services/tools/openrouter_image_tools.py`, схема tool в `services/tools/model_tools/generate_image_openrouter_tool.py`.
- **Ключ API:** только переменная окружения `OPENROUTER_API_KEY` (или pydantic `Settings.openrouter_api_key` из `.env`). В коде секретов нет.
- Дополнительно: `OPENROUTER_BASE_URL` (по умолчанию `https://openrouter.ai/api/v1`), `OPENROUTER_IMAGE_MODEL` (по умолчанию `google/gemini-2.5-flash-image`), опционально `OPENROUTER_HTTP_REFERER`.
- HTTP: `POST /chat/completions` с `modalities: ["image", "text"]`; картинки в `choices[0].message.images[].image_url.url` (часто data URI).
- Проверка: `python scripts/test_openrouter_image.py --prompt "test frame"` (нужен ключ в окружении).

## Видео Wan 2.7 — `image_to_video`

- Клиент: `services/video/wan_i2v_client.py`.
- Для **`wan2.7-i2v`** тело запроса использует `input.media`:
  - **`first_frame`** — стартовый кадр (`image_url` в tool);
  - **`last_frame`** — опционально конечный ключевой кадр (`last_frame_url` в tool), второй элемент в `media`.
- Старые модели с `input.img_url` получают только первый кадр; если передан `last_frame_url`, он логируется как игнорируемый.
- Асинхронная доставка: `VideoJobService` + коллекция `video_jobs`.
- Ручной прогон: `scripts/test_wan_video.py` (опция `--last-frame-url` для пары кадров).

## Типовая логика Сборщика

1. Нужны **оба кадра** (начало и конец шота): два вызова `generate_image_openrouter` (или один батч в будущем) → затем `image_to_video` с `image_url` и `last_frame_url`.
2. **Продолжение** предыдущей сцены: `last_frame_as_reference` по URL предыдущего видео → полученный кадр как новый `image_url` для i2v.
3. **Обрезка** разгона: после рендера `video_trim_start`.

Подробности по dev UI planning layer: вкладка «Сборщик» в `ui/dev/templates/partials/dream_stage1_prompt_lab.html`.
