"""LLM: сон → этапы pipeline (только JSON на каждом шаге)."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from core.config.settings import get_settings
from services.dreams.models import (
    DreamSceneItem,
    DreamSceneOutline,
    DreamScenePlan,
)
from services.llm.openai_chat_service import OpenAIChatService
from services.llm.system_prompt_loader import merge_with_global_model_policy
from services.llm.system_prompt_loader import (
    read_dream_beat_planner_raw,
    read_dream_decomposition_raw,
    read_dream_image_prompts_raw,
    read_dream_scene_motion_decompose_raw,
)
from services.observability.beat_planner_diagnostics import append_beat_planner_run

logger = logging.getLogger(__name__)

_MAX_SCENES = 5
# Публичный лимит сцен на шаге 1 (для UI и документации).
MAX_DECOMPOSE_SCENES = _MAX_SCENES


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


SYSTEM_DECOMPOSE = """Ты не чат-ассистент, а компонент pipeline (planner). Этап 1 — Storyboard + motion intent.

Задача: разбить текст сна на N смысловых сцен (N от 1 до {max_scenes}). В каждой сцене: actors, статичное описание смысла И отдельно motion — что должно произойти в динамике видео (не финальный кадр).

Критично — поле motion:
- Описывает **динамику**: направление действия, фазу бита, намерение камеры. Это потом пойдёт в видео как инструкция; картинка (этап 2) — только стартовый кадр под это motion.
- Не дублируй в motion финальный «замороженный» итог кадра; опиши **как развивается** сцена от первого кадра.

Верни ТОЛЬКО один JSON-объект. Без markdown-ограждений, без комментариев, без текста до или после JSON.

Схема ответа:
{{
  "dream_summary": "краткое резюме сна одной фразой",
  "scenes": [
    {{
      "scene_index": 1,
      "title": "короткое название",
      "short_description": "1–2 предложения для UI",
      "scene_description": "смысл сцены (кто/где/что)",
      "character_requirement": "main_character | crowd | none",
      "environment_requirement": "ключевые слова окружения",
      "mood": "настроение",
      "duration_sec": 4,
      "camera_motion": true,
      "actors": ["имя_или_роль_1", "имя_или_роль_2"],
      "motion": {{
        "type": "approach | contact | movement | static",
        "description": "что происходит в движении от первого кадра; не финальный штиль",
        "camera_behavior": "zoom | follow | static",
        "timing": "start | mid | end"
      }}
    }}
  ]
}}

Запрещено в этом ответе:
- промпты для генерации картинки (visual_prompt) или сырой текст для API видео;
- выполнять этапы 2 или 3 pipeline вручную;
- любой текст вне JSON.

Правила:
- duration_sec: 4, 5 или 6.
- Не больше {max_scenes} сцен; меньше — допустимо и часто правильно.
""".format(max_scenes=_MAX_SCENES)


SYSTEM_BEAT_PLANNER = """Ты компонент pipeline: **Beat Planner** (этап 0A). По тексту сна построй `header_context` и плотный массив `beats` (крупные смысловые узлы).
Не добавляй motion, camera, overlap, duration, image/visual/animation поля. Верни только JSON по контракту из user-сообщения.
Ориентир числа beats: не больше {max_scenes}.""".format(
    max_scenes=_MAX_SCENES
)

SYSTEM_SCENARIST_FALLBACK = """Ты — Сценарист Dream Pipeline: по header_context и beats сформируй связные scenes. header_context не меняй. Верни только JSON по контракту из user."""


def _decompose_system_prompt() -> str:
    """Production: сцены + motion — `prompts/dream_scene_motion_decompose.md` или SYSTEM_DECOMPOSE."""
    raw = read_dream_scene_motion_decompose_raw()
    text = (raw or "").strip()
    if not text:
        return SYSTEM_DECOMPOSE
    try:
        return text.format(max_scenes=_MAX_SCENES)
    except (KeyError, ValueError):
        return text


def _beat_planner_system_prompt() -> str:
    """Dev 0A / Beat Planner: `prompts/dream_beat_planner.md` или SYSTEM_BEAT_PLANNER."""
    raw = read_dream_beat_planner_raw()
    text = (raw or "").strip()
    if not text:
        return SYSTEM_BEAT_PLANNER
    try:
        return text.format(max_scenes=_MAX_SCENES)
    except (KeyError, ValueError):
        return text


def _scenarist_system_prompt() -> str:
    """Сценарист 0B: `prompts/dream_decomposition.md`; пусто — короткий fallback."""
    raw = read_dream_decomposition_raw()
    text = (raw or "").strip()
    if not text:
        return SYSTEM_SCENARIST_FALLBACK
    try:
        return text.format(max_scenes=_MAX_SCENES)
    except (KeyError, ValueError):
        return text


# Только если `prompts/dream_image_prompts.md` пуст или отсутствует.
_FALLBACK_DREAM_IMAGE_PROMPTS = """Ты не чат-ассистент, а компонент pipeline (prompt generator). Этап 2 из 2 — только Image Prompt.

Задача: для каждой уже спланированной сцены задать промпт **стартового кадра** для последующей анимации и намерение по референсу персонажа.

Критично — роль картинки:
- Изображение — это **первый кадр (keyframe)** клипа: момент **начала** или **ранней фазы** действия из поля `motion`, а **не** финальный «замороженный» итог (например не середина/конец объятия — а подход, разомкнутые объятия, начало движения).
- Согласуй кадр с `motion.type`, `motion.timing` и `motion.description`: камера и позы должны оставлять место для движения в видео.
- `scene_description` в данных — про смысл сцены; твой visual всё равно должен быть **стартовым состоянием** под заданное motion.

Верни ТОЛЬКО один JSON-объект. Без markdown, без текста вне JSON.

Схема:
{{
  "visual_prompts": [
    {{
      "scene_index": 1,
      "visual_prompt": "кинематографичное описание первого кадра (старт бита)",
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
- Не включай сюда отдельный текст анимации — движение уже задано в `motion` на этапе декомпозиции.
""".strip()


def _image_prompts_system() -> str:
    """System для шага 2: `prompts/dream_image_prompts.md` или встроенный _FALLBACK_DREAM_IMAGE_PROMPTS."""
    raw = (read_dream_image_prompts_raw() or "").strip()
    return raw if raw else _FALLBACK_DREAM_IMAGE_PROMPTS


def _asset_ctx_short(asset_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "has_face": asset_context.get("has_face"),
        "has_base_character": asset_context.get("has_base_character"),
        "secondary_actors": [
            {
                "actor_name": (a.get("actor_name") or ""),
                "asset_id": a.get("_id"),
            }
            for a in (asset_context.get("secondary_actors") or [])[:5]
        ],
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
    model: str | None = None,
) -> tuple[str, list[DreamSceneOutline]]:
    """Шаг 1: только сцены (без промптов изображения/анимации).

    `model` — только для этого вызова (например OPENAI_MODEL_DREAM_DECOMPOSE).
    """
    if not openai.configured:
        raise RuntimeError("OPENAI_API_KEY не задан — нельзя построить план сцен")

    dt = dream_text.strip()
    ctx_line = json.dumps(_asset_ctx_short(asset_context), ensure_ascii=False)
    system_prompt = _decompose_system_prompt()
    user_input = f"Контекст ассетов: {ctx_line}\n\nТекст сна:\n{dt}"
    assembled_prompt = json.dumps(
        [
            {"role": "system", "content": merge_with_global_model_policy(system_prompt)},
            {"role": "user", "content": user_input},
        ],
        ensure_ascii=False,
        indent=2,
    )
    model_id = (model or openai.default_model).strip() or openai.default_model
    settings = get_settings()
    temperature = settings.openai_dream_decompose_temperature
    max_tokens = settings.openai_dream_decompose_max_tokens
    seed = settings.openai_dream_decompose_seed
    raw = await openai.json_completion(
        system=system_prompt,
        user=user_input,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        seed=seed,
    )
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        append_beat_planner_run(
            {
                "source": "pipeline_stage0_decompose",
                "mode": "pipeline",
                "model_id": model_id,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "seed": seed,
                "system_prompt": system_prompt,
                "user_input": user_input,
                "assembled_prompt": assembled_prompt,
                "raw_response": raw,
                "parsed_response": None,
                "parse_error": str(e),
                "openai_model_default": settings.openai_model,
                "openai_model_dream_decompose": settings.openai_model_dream_decompose,
                "dev_debug_ui_enabled": settings.dev_debug_ui_enabled,
            }
        )
        logger.warning("dream_scene_planner step1: bad JSON: %s", e)
        raise RuntimeError("Модель вернула невалидный JSON (шаг: сцены)") from e
    append_beat_planner_run(
        {
            "source": "pipeline_stage0_decompose",
            "mode": "pipeline",
            "model_id": model_id,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "seed": seed,
            "system_prompt": system_prompt,
            "user_input": user_input,
            "assembled_prompt": assembled_prompt,
            "raw_response": raw,
            "parsed_response": data,
            "openai_model_default": settings.openai_model,
            "openai_model_dream_decompose": settings.openai_model_dream_decompose,
            "dev_debug_ui_enabled": settings.dev_debug_ui_enabled,
        }
    )

    outlines: list[DreamSceneOutline] = []
    for i, s in enumerate((data.get("scenes") or [])[:_MAX_SCENES], start=1):
        if not isinstance(s, dict):
            continue
        s = dict(s)
        s.setdefault("scene_index", i)
        if not (s.get("short_description") or "").strip():
            s["short_description"] = ((s.get("scene_description") or "")[:400]).strip()
        if not isinstance(s.get("motion"), dict):
            s["motion"] = {}
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
        system=_image_prompts_system(),
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


def animation_prompt_from_motion(o: DreamSceneOutline) -> str:
    """Текст для video job: только из motion + сцены Stage 0 (без отдельного LLM)."""
    m = o.motion
    core = (m.description or "").strip()
    if not core:
        core = (o.scene_description or o.short_description or "").strip()[:700]
    if not core:
        core = "Subtle motion continuing from the still frame."
    return (
        f"{core} "
        f"Motion class: {m.type}. Camera intent: {m.camera_behavior}. "
        f"Beat phase: {m.timing}. "
        "The input image is frame 0 — continue this motion naturally; "
        "do not describe or jump to a contradictory end pose."
    ).strip()


def merge_scene_plan(
    dream_summary: str,
    outlines: list[DreamSceneOutline],
    vp_map: dict[int, tuple[str, str]],
) -> DreamScenePlan:
    """Сборка плана: visual из LLM шага 2; анимация — только из motion (Stage 0)."""
    items: list[DreamSceneItem] = []
    for o in outlines:
        vp_row = vp_map.get(o.scene_index)
        ref_t = ""
        if vp_row:
            vp_raw, ref_t = vp_row[0], vp_row[1]
        else:
            vp_raw = ""
        vp = vp_raw.strip() or (
            f"Cinematic opening frame (start of beat): "
            f"{o.scene_description or o.short_description}"[:1200]
        )

        ap = animation_prompt_from_motion(o)
        duration_sec = _clamp_duration_sec(o.duration_sec, o.duration_sec)

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
                motion=o.motion,
                animation_prompt=ap,
                duration_sec=duration_sec,
                camera_motion=o.camera_motion,
                actors=list(o.actors or []),
            )
        )
    return DreamScenePlan(scenes=items, dream_summary=dream_summary[:500])


async def plan_dream_scenes_phased(
    *,
    openai: OpenAIChatService,
    dream_text: str,
    asset_context: dict[str, Any],
    decompose_model: str | None = None,
) -> DreamScenePlan:
    """Вызовы подряд без персиста между шагами (тесты / простой путь)."""
    dream_summary, outlines = await decompose_dream_scenes(
        openai=openai,
        dream_text=dream_text,
        asset_context=asset_context,
        model=decompose_model,
    )
    vp_map = await build_visual_prompts_for_scenes(
        openai=openai,
        dream_text=dream_text,
        dream_summary=dream_summary,
        outlines=outlines,
        asset_context=asset_context,
    )
    return merge_scene_plan(dream_summary, outlines, vp_map)


async def plan_dream_scenes(
    *,
    openai: OpenAIChatService,
    dream_text: str,
    asset_context: dict[str, Any],
    decompose_model: str | None = None,
) -> DreamScenePlan:
    return await plan_dream_scenes_phased(
        openai=openai,
        dream_text=dream_text,
        asset_context=asset_context,
        decompose_model=decompose_model,
    )
