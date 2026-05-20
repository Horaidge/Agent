"""
Контекст для dev UI: mini lab первичной разметки сна (stage 1 decomposition).
"""
from __future__ import annotations

import json
from typing import Any

from services.dreams.dream_scene_planner import MAX_DECOMPOSE_SCENES, _asset_ctx_short
from services.observability.dream_director_playground import (
    default_keyframes_user_contract_markdown,
    default_references_user_contract_markdown,
)
from services.llm.system_prompt_loader import (
    read_dream_director_keyframes_raw,
    read_dream_director_keyframes_user_contract_raw,
    read_dream_director_references_raw,
    read_dream_director_references_user_contract_raw,
    read_dream_image_prompts_raw,
)
from services.observability.tools_dev import prompt_file_meta, read_policy_files
from services.tools.openai_definitions import OPENAI_TOOLS_CATALOG


def build_dream_stage1_lab_context() -> dict[str, Any]:
    """
    Примеры входа/выхода совпадают с реальными строками в decompose_dream_scenes /
    build_visual_prompts_for_scenes (формат user-сообщения к модели).
    """
    policies = read_policy_files()
    dbeat_raw = policies.get("dream_beat_planner") or ""
    dm_raw = policies.get("dream_decomposition") or ""
    di_raw = read_dream_image_prompts_raw()
    dref_raw = read_dream_director_references_raw()
    dkf_raw = read_dream_director_keyframes_raw()
    dref_contract_raw = read_dream_director_references_user_contract_raw()
    dkf_contract_raw = read_dream_director_keyframes_user_contract_raw()
    dref_contract_editor = (
        dref_contract_raw
        if (dref_contract_raw or "").strip()
        else default_references_user_contract_markdown()
    )
    dkf_contract_editor = (
        dkf_contract_raw
        if (dkf_contract_raw or "").strip()
        else default_keyframes_user_contract_markdown()
    )

    # Репрезентативный asset_context (как в runtime после UserContext)
    example_asset_ctx: dict[str, Any] = {
        "has_face": True,
        "has_base_character": True,
        "secondary_actors": [
            {"actor_name": "Отец", "asset_id": "673a1b2c3d4e5f6789012345"},
        ],
        "missing": [],
        "environment_assets": [
            {
                "_id": "674b2c3d4e5f67890123456",
                "asset_type": "environment",
            }
        ],
    }
    ctx_short = _asset_ctx_short(example_asset_ctx)
    ctx_line = json.dumps(ctx_short, ensure_ascii=False)

    example_dream_text = (
        "Мы с детьми на какой-то ярмарке или в парке культуры. Весна, кругом снег. Сугробы. "
        "Дети просят купить напитки в открытом киоске. Даже не киоск, а просто стол посреди сугроба. "
        "На нём образцы напитков и закусок с ценниками. Кто-то, я не понимаю кто, но кто-то явно близкий "
        "мужчина, возможно, отец подружки детей, просит купить ему кусок пиццы. Стоит очередь. На столе рядом "
        "с кассой объявление: у кого мелкие деньги и без сдачи, обслуживается вне очереди. У меня набирается "
        "нужная сумма. Вот тут то этот мужчина и говорит: и мне пиццу, одна из дочек помогает мне, добавляя денег. "
        "Мы рассчитываемся. Я не понимаю, откуда продавец будет брать всё, что я заказал. Но тут неожиданно в небесах "
        "появляется вертолёт. И сбрасывает по наклонной сети наш заказ. Я забираю его, но детей рядом нет. Они куда-то "
        "убежали. Я иду в свою берлогу, Она вырыта в снегу неподалёку. И тут слышу голос детей. Разворачиваюсь и иду к ним "
        "по снежным тоннелям на их голоса."
    )

    stage1_user_message = (
        f"Контекст ассетов: {ctx_line}\n\nТекст сна:\n{example_dream_text.strip()}"
    )

    scenarist_output_example: dict[str, Any] = {
        "header_context": {
            "summary": "Ночной мост, отец впереди, паралич и пробуждение.",
            "environment": {
                "world_summary": "Ночной мокрый мост над водой, дождь, нестабильная опора и тревожный свет.",
            },
            "entities": [
                {"env_id": "bridge", "title": "Мост", "description": "Длинный мокрый мост с перилами над водой"},
                {"env_id": "water", "title": "Вода", "description": "Тёмная вода с отражениями и глубиной"},
            ],
            "world_properties": ["ночь", "дождь", "скользкая поверхность", "ощущение неустойчивости"],
            "meta": {"bits_total": 3},
        },
        "scenes": [
            {
                "scene_index": 1,
                "title": "Мост",
                "short_description": "Герой идёт по мокрому мосту ночью.",
                "scene_description": "Первое лицо: иду по скользким доскам, вокруг темнота и отражения.",
                "character_requirement": "main_character",
                "environment_requirement": "ночной мост, дождь, отражения",
                "mood": "тревога",
                "duration_sec": 5,
                "camera_motion": True,
                "actors": ["я"],
                "motion": {
                    "type": "movement",
                    "description": "Движение вперёд по мосту в глубину кадра; дождь и отражения — не финальный стоп-кадр, а начало бита.",
                    "camera_behavior": "follow",
                    "timing": "start",
                },
            },
            {
                "scene_index": 2,
                "title": "Отец",
                "short_description": "Впереди отец у перил.",
                "scene_description": "Силуэт отца спиной; вода под мостом.",
                "character_requirement": "main_character",
                "environment_requirement": "те же перила и вода",
                "mood": "напряжение",
                "duration_sec": 5,
                "camera_motion": False,
                "actors": ["я", "Отец"],
                "motion": {
                    "type": "approach",
                    "description": "Сокращение дистанции до отца; намерение дойти до контакта — кадр для картинки = ранняя фаза подхода, не объятие.",
                    "camera_behavior": "static",
                    "timing": "mid",
                },
            },
            {
                "scene_index": 3,
                "title": "Пробуждение",
                "short_description": "Мост исчезает — конец сна.",
                "scene_description": "Кадр без опоры, ощущение падения, резкий переход к белому свету.",
                "character_requirement": "main_character",
                "environment_requirement": "абстракция, белый свет",
                "mood": "облегчение",
                "duration_sec": 4,
                "camera_motion": True,
                "actors": ["я"],
                "motion": {
                    "type": "movement",
                    "description": "Рассыпание опоры и переход к пробуждению; динамика «падения» к свету, не застывший финал.",
                    "camera_behavior": "zoom",
                    "timing": "end",
                },
            },
        ],
    }

    header_context = scenarist_output_example["header_context"]
    dream_summary = str(header_context.get("summary") or "")
    outline_payload = scenarist_output_example["scenes"]

    distinct_actor_order: list[str] = []
    actor_scene_indices: dict[str, list[int]] = {}
    for sc in outline_payload:
        si = int(sc.get("scene_index") or 0)
        for raw in sc.get("actors") or []:
            name = str(raw)
            if name not in distinct_actor_order:
                distinct_actor_order.append(name)
            actor_scene_indices.setdefault(name, []).append(si)

    stage2_user_message = (
        f"Header Context (JSON):\n{json.dumps(header_context, ensure_ascii=False)}\n\n"
        f"Сцены (JSON):\n{json.dumps(outline_payload, ensure_ascii=False)}\n\n"
        f"Режим: Full JSON. Обрабатывай header_context и весь массив сцен за один проход."
    )
    stage2_output_example = {
        "visual_prompts": [
            {
                "scene_index": 1,
                "visual_prompt": "Ночной мокрый мост, герой в ранней фазе движения вперёд; кадр оставляет запас для дальнейшего прохода.",
                "image_prompt": "Cinematic first frame: rainy night bridge, protagonist beginning to move forward, reflective wet boards, room for continued motion.",
                "reference_type": "base_character",
            },
            {
                "scene_index": 2,
                "visual_prompt": "Герой в средней фазе подхода к отцу у перил, без финального контакта.",
                "image_prompt": "Cinematic first frame: protagonist approaching father at bridge railing, medium distance, pre-contact phase.",
                "reference_type": "base_character",
            },
            {
                "scene_index": 3,
                "visual_prompt": "Начало распада моста и переход к белому свету; ранняя фаза падения.",
                "image_prompt": "Cinematic first frame: bridge starting to dissolve into white light, early transition to awakening.",
                "reference_type": "none",
            },
        ]
    }

    director_input_schema = {
        "dream_text": (
            "исходный текст сна (сырой, как от пользователя); ground truth рядом с header_context и scenes"
        ),
        "header_context": {
            "summary": "string",
            "environment": {"world_summary": "string"},
            "entities": [{"env_id": "string", "title": "string", "description": "string"}],
            "world_properties": ["string"],
            "meta": {"bits_total": 0},
        },
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
                "key_objects_or_entities": ["string"],
            }
        ],
    }
    director_output_schema_v2 = {
        "director_planning": "v2",
        "dream_text": "тот же сырой текст, что на входе режиссёра (для Сборщика и воспроизводимости)",
        "header_context": "passthrough",
        "playground_policy": "строка из бэкенда",
        "asset_context": "симуляция UserContext / dream_assets (Playground)",
        "global_references": {
            "status": "pending_confirmation",
            "items": [
                {
                    "ref_id": "string",
                    "kind": "character|environment|object",
                    "label": "string",
                    "is_main_hero": True,
                    "user_has_reference": False,
                    "existing_asset_note": "null|string",
                    "generation_prompt": "string",
                    "rationale": "string",
                }
            ],
        },
        "key_frames": {
            "status": "pending_confirmation",
            "items": [
                {
                    "frame_index": 1,
                    "moment_description": "string",
                    "subjects_in_frame": ["string"],
                    "environment": "string",
                    "visual_focus": "string",
                    "hero_state": "string",
                    "uses_reference_ids": ["ref_id"],
                    "image_prompt": "string",
                    "scene_boundary": "new_scene|continues_previous",
                    "continues_from_frame_index": None,
                    "source_scene_indices": [1],
                    "video_bridge_prompt": "string",
                }
            ],
        },
        "video_plan": {
            "status": "pending_confirmation",
            "segments": [{"from_frame_index": 1, "to_frame_index": 2, "link_note": "string"}],
            "scene_flow": [{"frame_index": 1, "narrative_role": "string", "note": "string"}],
        },
        "final_scenes": "после 1B: shim для Сборщика (legacy-формат), до 1A — []",
    }
    director_output_schema_legacy = {
        "header_context": "passthrough — тот же объект, что на входе",
        "final_scenes": [
            {
                "scene_index": 1,
                "source_beat_index": 1,
                "title": "string",
                "scene_moment": "string",
                "actors": ["string"],
                "visual_focus": "string",
                "what_to_generate": "string",
                "overlap": False,
                "dependency_scene_index": None,
                "generation_strategy": "new_start|continue_from_previous",
                "motion_intensity": "static|light|active",
                "trim_sec": 0.0,
                "references": [{"kind": "character|last_frame|environment", "source": "string", "note": "string"}],
                "reference_source": "user_reference|generated_image|last_frame|none",
                "reference_image_url": "string",
                "visual_prompt": "string",
                "image_prompt": "string",
                "animation_prompt": "string",
                "reference_type": "base_character|selected_character|environment|none",
            }
        ],
    }

    stage0a_input_contract = {
        "_comment": "Форма sandbox: dream_text + asset_context_json (объект как в UserContext)",
        "dream_text": "string",
        "asset_context": {
            "has_face": "boolean?",
            "has_base_character": "boolean?",
            "secondary_actors": [{"actor_name": "string", "asset_id": "string"}],
            "missing": ["string"],
            "environment_hints": [["asset_type", "asset_id"]],
            "environment_assets": "optional — как в runtime",
        },
    }
    stage0a_output_contract = {
        "header_context": {
            "summary": "string",
            "environment": {"world_summary": "string"},
            "entities": [{"env_id": "string", "title": "string", "description": "string"}],
            "world_properties": ["string"],
            "meta": {"bits_total": 0},
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
                "story_function": "setup|escalation|transition|danger|discovery|climax|resolution",
            }
        ],
    }
    stage0b_input_contract = {
        "_note": "Тот же объект, что output 0A (beats + header_context)",
        "header_context": stage0a_output_contract["header_context"],
        "beats": stage0a_output_contract["beats"],
    }
    stage0b_output_contract = {
        "header_context": "passthrough без изменений",
        "scenes": director_input_schema["scenes"],
    }

    tools_by_name: dict[str, dict[str, Any]] = {}
    for schema in OPENAI_TOOLS_CATALOG:
        fn = (schema.get("function") or {})
        name = str(fn.get("name") or "").strip()
        if name:
            tools_by_name[name] = {
                "name": name,
                "description": str(fn.get("description") or ""),
                "parameters": (fn.get("parameters") or {}),
            }

    # Режиссёр только размечает план; инструменты исполнения закреплены за Сборщиком.
    director_tools: list[dict[str, Any]] = []

    assembler_tool_names = [
        "generate_image_openrouter",
        "image_to_video",
        "video_trim_start",
        "last_frame_as_reference",
    ]
    assembler_tools = [tools_by_name[n] for n in assembler_tool_names if n in tools_by_name]

    assembler_labels = {
        "generate_image_openrouter": "Изображение через OpenRouter",
        "image_to_video": "Видео Wan 2.7 (image-to-video)",
        "video_trim_start": "Обрезка начала клипа",
        "last_frame_as_reference": "Последний кадр как референс",
    }
    assembler_tools_for_ui: list[dict[str, Any]] = []
    for n in assembler_tool_names:
        if n not in tools_by_name:
            continue
        fn = tools_by_name[n]
        assembler_tools_for_ui.append(
            {
                "name": n,
                "label": assembler_labels.get(n, n),
                "blurb": str(fn.get("description") or ""),
            }
        )

    director_agent_bundle = {
        "role": "director_planner_storyboard_v2",
        "note": (
            "Режиссёр (Playground v2): два LLM-этапа без генерации медиа. "
            "В user всегда передаётся dream_text (исходный текст сна) + header_context + scenes; "
            "1A — global_references; 1B — key_frames + video_plan; final_scenes — только shim для Сборщика. "
            "Режим legacy: один выход final_scenes через prompts/dream_image_prompts.md."
        ),
        "director_input_json_contract": director_input_schema,
        "director_output_json_contract_v2": director_output_schema_v2,
        "director_output_json_contract_legacy": director_output_schema_legacy,
    }

    assembler_agent_bundle = {
        "assembler_execution_tools": assembler_tools,
        "assembler_input": (
            "Минимум: header_context + final_scenes (shim). "
            "Полный JSON Режиссёра v2 может содержать global_references и key_frames для прозрачности."
        ),
        "assembler_role": (
            "По плану Режиссёра вызывает инструменты: кадры через OpenRouter, "
            "видео через Wan 2.7, обрезку, извлечение last frame для continuation."
        ),
    }

    assembler_default_logic = (
        "Если у сцены нужны и начальный, и конечный кадр: сначала два вызова "
        "generate_image_openrouter (или один с разными промптами из image_prompt), "
        "затем image_to_video с image_url = первый кадр и last_frame_url = второй.\n"
        "Если generation_strategy = continue_from_previous или overlap: взять последний кадр "
        "предыдущего видео (last_frame_as_reference) и использовать как новый стартовый кадр "
        "для i2v или для следующей генерации изображения.\n"
        "Если trim_sec > 0: после рендера вызвать video_trim_start.\n"
        "Основной i2v: модель wan2.7-i2v."
    )

    assembler_sandbox_system_default = (
        "Ты — Сборщик (execution agent) для визуализации сна. На входе JSON Режиссёра: "
        "при наличии поле dream_text — исходный текст сна (детали и атмосфера); "
        "header_context и final_scenes с промптами и стратегиями кадров; "
        "global_references и key_frames — для связи референсов с кадрами.\n"
        "Следуй текстовой логике оператора ниже. Вызывай инструменты только из разрешённого набора. "
        "Для кадров используй generate_image_openrouter с полями из сцен (image_prompt / visual_prompt). "
        "Для роликов — image_to_video: нужны prompt, image_url (и при необходимости last_frame_url). "
        "После вызовов инструментов кратко опиши, что сделано, и что осталось.\n"
        "Не выдумывай URL изображений: бери их только из результатов tools."
    )

    beat_output_example = {
        "header_context": {
            "summary": dream_summary,
            "environment": {
                "world_summary": "Ночной мокрый мост над водой, дождь, нестабильная опора и тревожный свет.",
            },
            "entities": [
                {"env_id": "bridge", "title": "Мост", "description": "Длинный мокрый мост с перилами над водой"},
                {"env_id": "water", "title": "Вода", "description": "Тёмная вода с отражениями и глубиной"},
            ],
            "world_properties": ["ночь", "дождь", "скользкая поверхность", "ощущение неустойчивости"],
            "meta": {"bits_total": 3},
        },
        "beats": [
            {
                "beat_index": 1,
                "title": "Ночной мост",
                "beat_description": "Герой идёт по мокрому мосту и чувствует нарастающую тревогу.",
                "actors": ["я"],
                "environment": "ночной мост, дождь, отражения",
                "story_function": "setup",
            },
            {
                "beat_index": 2,
                "title": "Фигура отца",
                "beat_description": "Впереди появляется отец у перил, фокус сна смещается на недосказанный контакт.",
                "actors": ["я", "Отец"],
                "environment": "перила над водой, темнота",
                "story_function": "escalation",
            },
            {
                "beat_index": 3,
                "title": "Распад опоры",
                "beat_description": "Мост исчезает, начинается переход к пробуждению через ощущение провала и света.",
                "actors": ["я"],
                "environment": "абстрактный свет, исчезающее пространство",
                "story_function": "resolution",
            },
        ],
    }

    return {
        "dream_beat_planner_content": dbeat_raw,
        "dream_decomposition_content": dm_raw,
        "dream_image_content": di_raw,
        "dream_director_references_content": dref_raw,
        "dream_director_keyframes_content": dkf_raw,
        "dream_director_references_contract_content": dref_contract_editor,
        "dream_director_keyframes_contract_content": dkf_contract_editor,
        "dream_director_references_contract_meta": prompt_file_meta(dref_contract_raw),
        "dream_director_keyframes_contract_meta": prompt_file_meta(dkf_contract_raw),
        "dream_decomp_prompt_meta": prompt_file_meta(dm_raw),
        "dream_beat_planner_prompt_meta": prompt_file_meta(dbeat_raw),
        "max_decompose_scenes": MAX_DECOMPOSE_SCENES,
        "stage1_user_message_example": stage1_user_message,
        "stage1_output_json_example": json.dumps(scenarist_output_example, ensure_ascii=False, indent=2),
        "stage2_user_message_example": stage2_user_message,
        "stage2_output_json_example": json.dumps(
            stage2_output_example, ensure_ascii=False, indent=2
        ),
        "stage0_beats_output_example": beat_output_example,
        "stage0_beats_output_json_example": json.dumps(
            beat_output_example, ensure_ascii=False, indent=2
        ),
        "ctx_line_example": ctx_line,
        "stage1_ctx_short": ctx_short,
        "stage1_example_scenes": outline_payload,
        "stage1_dream_summary": dream_summary,
        "stage1_example_dream_text": example_dream_text.strip(),
        "stage1_distinct_actors": distinct_actor_order,
        "stage1_actor_scene_indices": actor_scene_indices,
        "example_dream_text": example_dream_text,
        "director_tools_json": json.dumps(director_tools, ensure_ascii=False, indent=2),
        "assembler_tools_json": json.dumps(assembler_tools, ensure_ascii=False, indent=2),
        "assembler_tools_for_ui": assembler_tools_for_ui,
        "assembler_default_logic": assembler_default_logic,
        "assembler_sandbox_system_default": assembler_sandbox_system_default,
        "director_input_json_contract": json.dumps(
            director_input_schema, ensure_ascii=False, indent=2
        ),
        "director_output_json_contract": json.dumps(
            director_output_schema_v2, ensure_ascii=False, indent=2
        ),
        "director_output_json_contract_legacy": json.dumps(
            director_output_schema_legacy, ensure_ascii=False, indent=2
        ),
        "director_agent_bundle_json": json.dumps(
            director_agent_bundle, ensure_ascii=False, indent=2
        ),
        "assembler_agent_bundle_json": json.dumps(
            assembler_agent_bundle, ensure_ascii=False, indent=2
        ),
        "stage0a_input_contract_json": json.dumps(stage0a_input_contract, ensure_ascii=False, indent=2),
        "stage0a_output_contract_json": json.dumps(stage0a_output_contract, ensure_ascii=False, indent=2),
        "stage0b_input_contract_json": json.dumps(stage0b_input_contract, ensure_ascii=False, indent=2),
        "stage0b_output_contract_json": json.dumps(stage0b_output_contract, ensure_ascii=False, indent=2),
    }
