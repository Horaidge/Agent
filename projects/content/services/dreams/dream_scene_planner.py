"""LLM: сон → этапы pipeline (только JSON на каждом шаге)."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from services.dreams.models import DreamSceneItem, DreamSceneOutline, DreamScenePlan
from services.llm.openai_chat_service import OpenAIChatService

logger = logging.getLogger(__name__)

_MAX_SCENES = 5


def _norm_reference_type(raw: Any) -> str:
    x = str(raw or "").strip().lower()
    if x in ("base_character", "face", "none"):
        return x
    return ""


def _clamp_duration_sec(raw: Any, fallback: int) -> int:
    try:
        d = int(raw)
    except (TypeError, ValueError):
        d = int(fallback)
    return min(max(d, 4), 6)


SYSTEM_DECOMPOSE = """Ты не чат-ассистент, а компонент pipeline (planner). Этап 1 из 3 — только Planning.

Задача: разбить текст сна на 1–{max_scenes} смысловых сцен.

Верни ТОЛЬКО один JSON-объект. Без markdown-ограждений, без комментариев, без текста до или после JSON.

Схема ответа:
{{
  "dream_summary": "краткое резюме сна одной фразой",
  "scenes": [
    {{
      "scene_index": 1,
      "title": "короткое название",
      "short_description": "1–2 предложения для UI",
      "scene_description": "что происходит в сцене",
      "character_requirement": "main_character | crowd | none",
      "environment_requirement": "ключевые слова окружения",
      "mood": "настроение",
      "duration_sec": 4,
      "camera_motion": true
    }}
  ]
}}

Запрещено в этом ответе:
- промпты для картинки или видео;
- выполнять этапы 2 или 3;
- любой текст вне JSON.

Правила:
- duration_sec: 4, 5 или 6.
- Не больше {max_scenes} сцен.
""".format(max_scenes=_MAX_SCENES)

SYSTEM_IMAGE_PROMPTS = """Ты не чат-ассистент, а компонент pipeline (prompt generator). Этап 2 из 3 — только Image Prompt.

Задача: для каждой уже спланированной сцены задать промпт первого кадра и намерение по референсу персонажа.

Верни ТОЛЬКО один JSON-объект. Без markdown, без текста вне JSON.

Схема:
{{
  "visual_prompts": [
    {{
      "scene_index": 1,
      "visual_prompt": "кинематографичное описание кадра (допустимо то же поле как image_prompt)",
      "image_prompt": "необязательный дубликат visual_prompt — если задан, сервер использует его же",
      "reference_type": "base_character | face | none"
    }}
  ]
}}

Поле reference_type:
- base_character — опираться на базового персонажа, если он есть в контексте;
- face — на загруженное лицо пользователя, если есть;
- none — без референса лица, только текст.

Правила:
- Один объект на каждую scene_index из входного списка сцен.
- visual_prompt (или image_prompt) должен быть согласован между сценами (один герой, если это один сон).
- Не включай сюда animation_prompt и не разбивай сон заново — только промпты картинок.
""".strip()

SYSTEM_ANIMATION_PROMPTS = """Ты не чат-ассистент, а компонент pipeline (prompt generator). Этап 3 из 3 — только Animation Prompt.

Задача: для каждой сцены — промпт анимации (Wan / видео) и длительность клипа.

Верни ТОЛЬКО один JSON-объект. Без markdown, без текста вне JSON.

Схема:
{{
  "animation_prompts": [
    {{
      "scene_index": 1,
      "animation_prompt": "кратко: движение, камера, динамика",
      "duration": 5
    }}
  ]
}}

Правила:
- Один объект на каждую scene_index из входного списка.
- duration — целое число секунд, обычно 4, 5 или 6 (как в плане сцены).
- animation_prompt — только суть движения, без воды.
- Не повторяй полный разбор сна и не генерируй промпты картинок — только анимация.
""".strip()


def _asset_ctx_short(asset_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "has_face": asset_context.get("has_face"),
        "has_base_character": asset_context.get("has_base_character"),
        "missing": asset_context.get("missing"),
        "environment_hints": [
            (a.get("asset_type"), a.get("_id"))
            for a in (asset_context.get("environment_assets") or [])[:5]
        ],
    }


async def decompose_dream_scenes(
    *,
    openai: OpenAIChatService,
    dream_text: str,
    asset_context: dict[str, Any],
) -> tuple[str, list[DreamSceneOutline]]:
    """Шаг 1: только сцены (без промптов изображения/анимации)."""
    if not openai.configured:
        raise RuntimeError("OPENAI_API_KEY не задан — нельзя построить план сцен")

    dt = dream_text.strip()
    ctx_line = json.dumps(_asset_ctx_short(asset_context), ensure_ascii=False)
    raw = await openai.json_completion(
        system=SYSTEM_DECOMPOSE,
        user=f"Контекст ассетов: {ctx_line}\n\nТекст сна:\n{dt}",
    )
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("dream_scene_planner step1: bad JSON: %s", e)
        raise RuntimeError("Модель вернула невалидный JSON (шаг: сцены)") from e

    outlines: list[DreamSceneOutline] = []
    for i, s in enumerate((data.get("scenes") or [])[:_MAX_SCENES], start=1):
        if not isinstance(s, dict):
            continue
        s = dict(s)
        s.setdefault("scene_index", i)
        if not (s.get("short_description") or "").strip():
            s["short_description"] = ((s.get("scene_description") or "")[:400]).strip()
        try:
            outlines.append(DreamSceneOutline.model_validate(s))
        except ValidationError as ve:
            logger.info("dream_scene_planner step1: skip invalid scene: %s", ve)

    if not outlines:
        raise RuntimeError("План сцен пуст — попробуйте другой текст сна")

    dream_summary = str(data.get("dream_summary") or "")[:500]
    return dream_summary, outlines


async def build_visual_prompts_for_scenes(
    *,
    openai: OpenAIChatService,
    dream_text: str,
    dream_summary: str,
    outlines: list[DreamSceneOutline],
    asset_context: dict[str, Any],
) -> dict[int, tuple[str, str]]:
    """Шаг 2: промпт картинки и reference_type на сцену."""
    ctx_line = json.dumps(_asset_ctx_short(asset_context), ensure_ascii=False)
    outline_payload = [o.model_dump() for o in outlines]
    raw = await openai.json_completion(
        system=SYSTEM_IMAGE_PROMPTS,
        user=(
            f"Контекст ассетов: {ctx_line}\n\n"
            f"Резюме сна: {dream_summary}\n\n"
            f"Сцены (JSON):\n{json.dumps(outline_payload, ensure_ascii=False)}\n\n"
            f"Полный текст сна:\n{dream_text.strip()}"
        ),
    )
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("dream_scene_planner step2: bad JSON: %s", e)
        raise RuntimeError("Модель вернула невалидный JSON (шаг: промпты картинок)") from e

    vp_map: dict[int, tuple[str, str]] = {}
    for item in data.get("visual_prompts") or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("scene_index"))
            v = (item.get("image_prompt") or item.get("visual_prompt") or "").strip()
            ref = _norm_reference_type(item.get("reference_type"))
            if idx and v:
                vp_map[idx] = (v, ref)
        except (TypeError, ValueError):
            continue
    return vp_map


async def build_animation_prompts_for_scenes(
    *,
    openai: OpenAIChatService,
    dream_text: str,
    outlines: list[DreamSceneOutline],
    visual_prompts_by_index: dict[int, tuple[str, str]],
    asset_context: dict[str, Any],
) -> dict[int, tuple[str, int]]:
    """Шаг 3: промпт анимации и duration (сек) на сцену."""
    ctx_line = json.dumps(_asset_ctx_short(asset_context), ensure_ascii=False)
    vp_list = [
        {
            "scene_index": o.scene_index,
            "visual_prompt": (visual_prompts_by_index.get(o.scene_index) or ("", ""))[0],
        }
        for o in outlines
    ]
    raw = await openai.json_completion(
        system=SYSTEM_ANIMATION_PROMPTS,
        user=(
            f"Контекст ассетов: {ctx_line}\n\n"
            f"Сцены с визуальными промптами:\n"
            f"{json.dumps(vp_list, ensure_ascii=False)}\n\n"
            f"Текст сна:\n{dream_text.strip()}"
        ),
    )
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("dream_scene_planner step3: bad JSON: %s", e)
        raise RuntimeError("Модель вернула невалидный JSON (шаг: промпты анимации)") from e

    ap_map: dict[int, tuple[str, int]] = {}
    outline_dur = {o.scene_index: o.duration_sec for o in outlines}
    for item in data.get("animation_prompts") or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("scene_index"))
            v = (item.get("animation_prompt") or "").strip()
            fb = outline_dur.get(idx, 5)
            dur = _clamp_duration_sec(item.get("duration"), fb)
            if idx and v:
                ap_map[idx] = (v, dur)
        except (TypeError, ValueError):
            continue
    return ap_map


def merge_scene_plan(
    dream_summary: str,
    outlines: list[DreamSceneOutline],
    vp_map: dict[int, tuple[str, str]],
    ap_map: dict[int, tuple[str, int]],
) -> DreamScenePlan:
    """Сборка финального плана с fallback, если модель пропустила индекс."""
    items: list[DreamSceneItem] = []
    for o in outlines:
        vp_row = vp_map.get(o.scene_index)
        ref_t = ""
        if vp_row:
            vp_raw, ref_t = vp_row[0], vp_row[1]
        else:
            vp_raw = ""
        vp = vp_raw.strip() or (
            f"Cinematic shot: {o.scene_description or o.short_description}"[:1200]
        )

        ap_row = ap_map.get(o.scene_index)
        if ap_row:
            ap_raw, dur_ai = ap_row[0], ap_row[1]
        else:
            ap_raw, dur_ai = "", o.duration_sec
        ap = ap_raw.strip() or (
            (o.scene_description or o.short_description or "slow camera movement")[:500]
        )
        duration_sec = _clamp_duration_sec(dur_ai, o.duration_sec)

        items.append(
            DreamSceneItem(
                scene_index=o.scene_index,
                title=o.title,
                short_description=o.short_description,
                scene_description=o.scene_description,
                visual_prompt=vp,
                reference_type=ref_t,
                character_requirement=o.character_requirement,
                environment_requirement=o.environment_requirement,
                mood=o.mood,
                animation_prompt=ap,
                duration_sec=duration_sec,
                camera_motion=o.camera_motion,
            )
        )
    return DreamScenePlan(scenes=items, dream_summary=dream_summary[:500])


async def plan_dream_scenes_phased(
    *,
    openai: OpenAIChatService,
    dream_text: str,
    asset_context: dict[str, Any],
) -> DreamScenePlan:
    """Три вызова подряд без персиста между шагами (тесты / простой путь)."""
    dream_summary, outlines = await decompose_dream_scenes(
        openai=openai,
        dream_text=dream_text,
        asset_context=asset_context,
    )
    vp_map = await build_visual_prompts_for_scenes(
        openai=openai,
        dream_text=dream_text,
        dream_summary=dream_summary,
        outlines=outlines,
        asset_context=asset_context,
    )
    ap_map = await build_animation_prompts_for_scenes(
        openai=openai,
        dream_text=dream_text,
        outlines=outlines,
        visual_prompts_by_index=vp_map,
        asset_context=asset_context,
    )
    return merge_scene_plan(dream_summary, outlines, vp_map, ap_map)


async def plan_dream_scenes(
    *,
    openai: OpenAIChatService,
    dream_text: str,
    asset_context: dict[str, Any],
) -> DreamScenePlan:
    return await plan_dream_scenes_phased(
        openai=openai,
        dream_text=dream_text,
        asset_context=asset_context,
    )
