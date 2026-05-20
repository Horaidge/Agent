"""
Playground · Режиссёр: два LLM-этапа без генерации медиа.

1) Глобальные референсы (персонажи, 1–3 окружения, важные объекты).
2) Ключевые кадры (сколько нужно сну) + план связей для будущего видео.
   Тексты user-контрактов (схема JSON + правила) — в каталоге contracts/ рядом с prompts/.

Сборщик и прод-пайплайн по-прежнему могут потребовать legacy final_scenes —
см. build_assembler_final_scenes_shim.
"""
from __future__ import annotations

import json
from typing import Any

from services.llm.system_prompt_loader import (
    read_dream_director_keyframes_user_contract_raw,
    read_dream_director_references_user_contract_raw,
)

PENDING = "pending_confirmation"
PLAYGROUND_POLICY = (
    "Режим Playground: нет доступа к реальной коллекции пользователя. "
    "Поля user_has_reference / existing_asset_note описывают ожидаемое поведение в проде "
    "(Mongo dream_assets, user_profiles). Не выдумывай реальные asset_id — только логику."
)


def director_dream_text_user_block(dream_text: str | None) -> str:
    """
    Фрагмент user-сообщения для режиссёра (1A/1B): исходный текст сна без изменений.
    Не JSON — сырой текст, как ввёл пользователь (Telegram / API / dev поле).
    """
    raw = dream_text if isinstance(dream_text, str) else ""
    if not (raw or "").strip():
        return (
            "Исходный текст сна (dream_text): в этом запуске не передан — опирайся на "
            "header_context и scenes. Для проверки режиссёра без потерь декомпозиции "
            "заполни поле «Исходный текст сна» во вкладке Режиссёр.\n\n"
        )
    return (
        "Исходный текст сна (dream_text) — сырой ввод пользователя (ground truth). "
        "Используй как дополнительный слой деталей, атмосферы и фактов; не подменяй им "
        "header_context и не переписывай сцены — это отдельные структурированные слои.\n"
        "--- dream_text (как ввёл пользователь) begin ---\n"
        f"{raw}\n"
        "--- dream_text end ---\n\n"
    )


_REFERENCES_USER_CONTRACT_FALLBACK = (
    "Верни JSON строго в формате:\n"
    "{\n"
    '  "global_references": {\n'
    f'    "status": "{PENDING}",\n'
    '    "items": [\n'
    "      {\n"
    '        "ref_id": "stable_snake_case_id",\n'
    '        "kind": "character|environment|object",\n'
    '        "label": "короткое имя",\n'
    '        "short_blurb": "1–2 предложения простым языком: кто/что это для зрителя (без технички)",\n'
    '        "is_main_hero": true,\n'
    '        "user_has_reference": false,\n'
    '        "existing_asset_note": null,\n'
    '        "generation_prompt": "компактный промпт для одной картинки-референса (без простыни)",\n'
    '        "rationale": "одна строка: зачем визуально (для команды; не для пользователя в UI)"\n'
    "      }\n"
    "    ]\n"
    "  },\n"
    '  "playground_notes": "кратко: что пользователь увидит до подтверждения генерации"\n'
    "}\n"
    "Правила:\n"
    "- Ты не генерируешь изображения и не вызываешь инструменты — только план.\n"
    "- Персонажи: минимум главный герой; второстепенные — только если влияют на визуал (не больше 4 персонажей в сумме).\n"
    "- Окружения: 1–3 ключевые зоны, не больше.\n"
    "- Объекты: только если без них визуал сна теряется; не раздувай список.\n"
    "- short_blurb обязателен: коротко и по-человечески; generation_prompt — только для картинки, без повторения всего сна.\n"
    "- user_has_reference: в Playground ставь false, если нет явного сигнала из asset_context; "
    "existing_asset_note тогда null или пояснение «в проде: проверка коллекции».\n"
    "- Если в asset_context указано has_base_character / has_face / secondary_actors — отрази это "
    "в user_has_reference и кратком existing_asset_note (без выдуманных id).\n"
)

_KEYFRAMES_USER_CONTRACT_FALLBACK = (
    "Верни JSON строго в формате:\n"
    "{\n"
    '  "key_frames": {\n'
    f'    "status": "{PENDING}",\n'
    '    "items": [\n'
    "      {\n"
    '        "frame_index": 1,\n'
    '        "short_label": "короткий заголовок кадра",\n'
    '        "moment_description": "что происходит прямо сейчас (одно действие или состояние)",\n'
    '        "subjects_in_frame": ["кто в кадре"],\n'
    '        "environment": "окружение / зона",\n'
    '        "visual_focus": "главный визуальный акцент",\n'
    '        "hero_state": "состояние героя (эмоция, поза, направление взгляда)",\n'
    '        "uses_reference_ids": ["ref_id из global_references"],\n'
    '        "image_prompt": "готовый промпт для генерации одного изображения этого кадра",\n'
    '        "scene_boundary": "new_scene|continues_previous",\n'
    '        "continues_from_frame_index": null,\n'
    '        "source_scene_indices": [1, 2],\n'
    '        "video_bridge_prompt": "краткая подсказка для будущего i2v между этим и следующим кадром или пустая строка"\n'
    "      }\n"
    "    ]\n"
    "  },\n"
    '  "video_plan": {\n'
    f'    "status": "{PENDING}",\n'
    '    "segments": [\n'
    "      {\n"
    '        "from_frame_index": 1,\n'
    '        "to_frame_index": 2,\n'
    '        "link_note": "как два кадра склеиваются визуально / по смыслу"\n'
    "      }\n"
    "    ],\n"
    '    "scene_flow": [\n'
    "      {\n"
    '        "frame_index": 1,\n'
    '        "narrative_role": "new_scene|continuation",\n'
    '        "note": "связь с сценарием сценариста"\n'
    "      }\n"
    "    ]\n"
    "  },\n"
    '  "playground_notes": "кратко: что будет сгенерировано после подтверждения"\n'
    "}\n"
    "Правила:\n"
    "- Не дублируй сценариста построчно: выдай полную цепочку визуальных моментов — столько кадров, "
    "сколько нужно, чтобы передать все существенные изменения, действия и повороты сна (без искусственного сжатия).\n"
    "- Один кадр = одно действие или одно устойчивое состояние.\n"
    "- continues_from_frame_index: номер предыдущего key frame, если scene_boundary=continues_previous.\n"
    "- video_plan.segments: какие пары кадров пойдут в связку видео (не обязательно все подряд).\n"
    "- ref_id в uses_reference_ids должны совпадать с планом global_references.\n"
)


def default_references_user_contract_markdown() -> str:
    """Дефолтный текст user-контракта 1A, если файл в contracts/ пуст или отсутствует."""
    return _REFERENCES_USER_CONTRACT_FALLBACK


def default_keyframes_user_contract_markdown() -> str:
    """Дефолтный текст user-контракта 1B, если файл в contracts/ пуст или отсутствует."""
    return _KEYFRAMES_USER_CONTRACT_FALLBACK


def references_contract_user_block() -> str:
    t = (read_dream_director_references_user_contract_raw() or "").strip()
    return t if t else _REFERENCES_USER_CONTRACT_FALLBACK


def keyframes_contract_user_block() -> str:
    t = (read_dream_director_keyframes_user_contract_raw() or "").strip()
    return t if t else _KEYFRAMES_USER_CONTRACT_FALLBACK


def _as_list(x: Any) -> list[Any]:
    return x if isinstance(x, list) else []


def _as_dict(x: Any) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def normalize_global_references_block(
    parsed: dict[str, Any],
    *,
    header_context: dict[str, Any],
) -> dict[str, Any]:
    raw = parsed.get("global_references")
    block = _as_dict(raw)
    items_in = _as_list(block.get("items"))
    items: list[dict[str, Any]] = []
    for it in items_in:
        if not isinstance(it, dict):
            continue
        rid = str(it.get("ref_id") or it.get("id") or "").strip() or f"ref_{len(items) + 1}"
        sb = str(it.get("short_blurb") or "").strip()
        rat = str(it.get("rationale") or "").strip()
        if not sb and rat:
            sb = (rat[:200] + "…") if len(rat) > 200 else rat
        items.append(
            {
                "ref_id": rid,
                "kind": str(it.get("kind") or "character").strip(),
                "label": str(it.get("label") or "").strip(),
                "short_blurb": sb,
                "is_main_hero": bool(it.get("is_main_hero")),
                "user_has_reference": bool(it.get("user_has_reference")),
                "existing_asset_note": it.get("existing_asset_note"),
                "generation_prompt": str(it.get("generation_prompt") or "").strip(),
                "rationale": rat,
                "preview_image_url": str(it.get("preview_image_url") or "").strip() or None,
            }
        )
    return {
        "status": str(block.get("status") or PENDING),
        "items": items,
        "header_context_echo": header_context,
    }


def normalize_key_frames_bundle(
    parsed: dict[str, Any],
    *,
    header_context: dict[str, Any],
    global_references: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    kf_raw = _as_dict(parsed.get("key_frames"))
    items_in = _as_list(kf_raw.get("items"))
    items: list[dict[str, Any]] = []
    for it in items_in:
        if not isinstance(it, dict):
            continue
        try:
            fi = int(it.get("frame_index") or len(items) + 1)
        except (TypeError, ValueError):
            fi = len(items) + 1
        cf = it.get("continues_from_frame_index")
        try:
            cf_int = int(cf) if cf is not None else None
        except (TypeError, ValueError):
            cf_int = None
        src_si = it.get("source_scene_indices")
        if not isinstance(src_si, list):
            src_si = []
        src_si_clean: list[int] = []
        for x in src_si:
            try:
                src_si_clean.append(int(x))
            except (TypeError, ValueError):
                continue
        items.append(
            {
                "frame_index": fi,
                "short_label": str(it.get("short_label") or "").strip(),
                "moment_description": str(it.get("moment_description") or "").strip(),
                "subjects_in_frame": [str(x) for x in _as_list(it.get("subjects_in_frame"))],
                "environment": str(it.get("environment") or "").strip(),
                "visual_focus": str(it.get("visual_focus") or "").strip(),
                "hero_state": str(it.get("hero_state") or "").strip(),
                "uses_reference_ids": [str(x) for x in _as_list(it.get("uses_reference_ids"))],
                "image_prompt": str(it.get("image_prompt") or "").strip(),
                "scene_boundary": str(it.get("scene_boundary") or "new_scene").strip(),
                "continues_from_frame_index": cf_int,
                "source_scene_indices": src_si_clean,
                "video_bridge_prompt": str(it.get("video_bridge_prompt") or "").strip(),
            }
        )
    items.sort(key=lambda r: r["frame_index"])
    key_frames = {
        "status": str(kf_raw.get("status") or PENDING),
        "items": items,
        "header_context_echo": header_context,
        "global_references_echo": global_references,
    }
    vp_raw = _as_dict(parsed.get("video_plan"))
    segments_in = _as_list(vp_raw.get("segments"))
    segments: list[dict[str, Any]] = []
    for seg in segments_in:
        if not isinstance(seg, dict):
            continue
        try:
            a = int(seg.get("from_frame_index") or 0)
            b = int(seg.get("to_frame_index") or 0)
        except (TypeError, ValueError):
            continue
        segments.append(
            {
                "from_frame_index": a,
                "to_frame_index": b,
                "link_note": str(seg.get("link_note") or "").strip(),
            }
        )
    flow_in = _as_list(vp_raw.get("scene_flow"))
    scene_flow: list[dict[str, Any]] = []
    for row in flow_in:
        if not isinstance(row, dict):
            continue
        try:
            fi = int(row.get("frame_index") or 0)
        except (TypeError, ValueError):
            continue
        scene_flow.append(
            {
                "frame_index": fi,
                "narrative_role": str(row.get("narrative_role") or "").strip(),
                "note": str(row.get("note") or "").strip(),
            }
        )
    video_plan = {
        "status": str(vp_raw.get("status") or PENDING),
        "segments": segments,
        "scene_flow": scene_flow,
    }
    notes = str(parsed.get("playground_notes") or "").strip()
    return key_frames, video_plan, notes


def build_assembler_final_scenes_shim(
    key_frames: dict[str, Any],
    video_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Совместимость с Сборщиком: плоский список final_scenes из key_frames."""
    items = _as_list(key_frames.get("items"))
    segments = _as_list(video_plan.get("segments"))
    segment_pairs = {(s.get("from_frame_index"), s.get("to_frame_index")) for s in segments if isinstance(s, dict)}

    rows: list[dict[str, Any]] = []
    for kf in items:
        if not isinstance(kf, dict):
            continue
        fi = int(kf.get("frame_index") or len(rows) + 1)
        boundary = str(kf.get("scene_boundary") or "new_scene")
        overlap = boundary == "continues_previous"
        dep = kf.get("continues_from_frame_index")
        try:
            dep_int = int(dep) if dep is not None else None
        except (TypeError, ValueError):
            dep_int = None
        refs = kf.get("uses_reference_ids") or []
        ref_objs = [{"kind": "planned_reference", "source": str(rid), "note": ""} for rid in refs]
        # Подсказка для анимации: мост к следующему кадру, если есть сегмент (fi -> next)
        vbridge = str(kf.get("video_bridge_prompt") or "").strip()
        next_targets = [b for (a, b) in segment_pairs if a == fi]
        animation = vbridge
        if next_targets and not animation:
            animation = f"bridge to frame {next_targets[0]}"
        rows.append(
            {
                "scene_index": fi,
                "source_beat_index": (kf.get("source_scene_indices") or [None])[0],
                "title": str(kf.get("short_label") or f"Кадр {fi}"),
                "scene_moment": str(kf.get("moment_description") or ""),
                "actors": list(kf.get("subjects_in_frame") or []),
                "visual_focus": str(kf.get("visual_focus") or ""),
                "what_to_generate": str(kf.get("image_prompt") or ""),
                "overlap": overlap,
                "dependency_scene_index": dep_int if overlap else None,
                "generation_strategy": "continue_from_previous" if overlap else "new_start",
                "motion_intensity": "light",
                "trim_sec": 0.0,
                "references": ref_objs,
                "reference_source": "none",
                "reference_type": "none",
                "reference_image_url": "",
                "visual_prompt": str(kf.get("moment_description") or ""),
                "image_prompt": str(kf.get("image_prompt") or ""),
                "animation_prompt": animation,
            }
        )
    return rows


def default_references_system_prompt() -> str:
    return (
        "Ты — режиссёр-планировщик сна (этап 1 из 2): глобальные визуальные референсы.\n"
        "Твоя задача — по header_context и сценам сценариста определить базовый набор визуальных опор "
        "(персонажи, 1–3 ключевых окружения, важные объекты), которые понадобятся для всего сна.\n"
        "Ты не генерируешь изображения и не описываешь финальные видео-шоты — только референсы и промпты для них.\n"
        "Ответ только JSON по контракту user-сообщения.\n"
    )


def default_keyframes_system_prompt() -> str:
    return (
        "Ты — режиссёр-планировщик сна (этап 2 из 2): раскадровка ключевых кадров.\n"
        "Ты не копируешь сценариста дословно — строишь раскадровку: столько ключевых кадров, сколько нужно для полной визуальной истории.\n"
        "Каждый кадр — одно изображение: одно действие или одно состояние.\n"
        "Используй ref_id из переданного плана global_references.\n"
        "Ты не генерируешь медиа — только план и готовые текстовые промпты.\n"
        "Ответ только JSON по контракту user-сообщения.\n"
    )


def parse_asset_context_playground(raw: str) -> dict[str, Any]:
    try:
        o = json.loads(raw or "{}")
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}
