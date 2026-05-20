"""Facade и контракты Dream Lite для управляемых стратегий."""
from __future__ import annotations

from typing import Any


DEFAULT_DREAM_LITE_RUN_CONFIG: dict[str, Any] = {
    "pipeline_variant": "pair_i2v_between_keyframes",
    "image_policy": {
        "provider": "openrouter",
        "mode": "text+image_refs",
        "model": "",
        "simple_mode": False,
    },
    "video_policy": {
        "backend_priority": ["dashscope", "openrouter"],
        "mode": "image+text",
        "prompt_mode": "first_last_frame",
        "montage_preset": "default",
        "audio_required": False,
        "i2v_model": "wan2.7-i2v",
        "duration_sec": 4,
        "resolution": "720p",
        "backend": "",
        "openrouter_model": "",
        # Препросев сегментов i2v и подтверждение монтажа (пресет Seedance поднимает stride и включает гейт).
        "scene_segment_stride": 1,
        "reference_frame_stride": 1,
        "require_montage_confirm": False,
    },
    "fallback_policy": {
        "on_i2v_data_inspection": "fail_run",
        "allow_text_to_video_fallback": False,
    },
    "steps": {
        "text_step1_system_prompt": "",
        "text_step2_system_prompt": "",
        "text_step2_prev_link_system_prompt": "",
        "transition_plan_system_prompt": "",
        "transition_plan_seedance_system_prompt": "",
        "transition_plan_wan26_system_prompt": "",
        "transition_plan_kling_reference_system_prompt": "",
    },
}


def video_policy_bundle_for_montage_preset(montage_preset: str) -> dict[str, Any]:
    """
    Согласованные поля video_policy для пресета монтажа.
    Не задаёт backend/model — их выбирает пользователь отдельно.
    """
    mp = str(montage_preset or "").strip().lower() or "default"
    if mp == "seedance":
        return {
            "montage_preset": "seedance",
            "duration_sec": 7,
            "resolution": "480x480",
            "scene_segment_stride": 2,
            "reference_frame_stride": 2,
            "require_montage_confirm": True,
        }
    if mp == "wan_2_6_single_anchor":
        return {
            "montage_preset": "wan_2_6_single_anchor",
            "duration_sec": 5,
            "resolution": "480x480",
            "scene_segment_stride": 1,
            "reference_frame_stride": 1,
            "require_montage_confirm": False,
        }
    if mp == "kling_v3_reference_motion":
        return {
            "montage_preset": "kling_v3_reference_motion",
            "duration_sec": 5,
            "resolution": "720x720",
            "scene_segment_stride": 1,
            "reference_frame_stride": 1,
            "require_montage_confirm": False,
        }
    return {
        "montage_preset": "default",
        "duration_sec": 4,
        "resolution": "720p",
        "scene_segment_stride": 1,
        "reference_frame_stride": 1,
        "require_montage_confirm": False,
    }


def default_run_config() -> dict[str, Any]:
    return {
        "pipeline_variant": DEFAULT_DREAM_LITE_RUN_CONFIG["pipeline_variant"],
        "image_policy": dict(DEFAULT_DREAM_LITE_RUN_CONFIG["image_policy"]),
        "video_policy": {
            "backend_priority": list(DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["backend_priority"]),
            "mode": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["mode"],
            "prompt_mode": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["prompt_mode"],
            "montage_preset": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["montage_preset"],
            "audio_required": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["audio_required"],
            "i2v_model": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["i2v_model"],
            "duration_sec": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["duration_sec"],
            "resolution": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["resolution"],
            "backend": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["backend"],
            "openrouter_model": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["openrouter_model"],
            "scene_segment_stride": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["scene_segment_stride"],
            "reference_frame_stride": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["reference_frame_stride"],
            "require_montage_confirm": DEFAULT_DREAM_LITE_RUN_CONFIG["video_policy"]["require_montage_confirm"],
        },
        "fallback_policy": dict(DEFAULT_DREAM_LITE_RUN_CONFIG["fallback_policy"]),
        "steps": dict(DEFAULT_DREAM_LITE_RUN_CONFIG["steps"]),
    }


def stage_contract_catalog() -> list[dict[str, Any]]:
    return [
        {"stage": "text_step1", "task": "env+char decomposition", "input_modalities": ["text"], "output_schema": ["step1_raw", "env_cards[]", "char_cards[]"]},
        {"stage": "text_step2", "task": "storyboard frames", "input_modalities": ["text"], "output_schema": ["step2_raw", "step2_prev_link_raw", "frame_cards[]"]},
        {"stage": "gen_env", "task": "environment images", "input_modalities": ["text"], "output_schema": ["generated_env[title].urls[]"]},
        {"stage": "gen_char", "task": "character sheets", "input_modalities": ["text"], "output_schema": ["generated_char[title].urls[]"]},
        {"stage": "gen_frame", "task": "keyframes", "input_modalities": ["text", "image"], "output_schema": ["generated_frames[].urls[]"]},
        {"stage": "transition_plan", "task": "transition planning", "input_modalities": ["text"], "output_schema": ["transition_plan.transitions[]"]},
        {"stage": "anim_i2v", "task": "image-to-video", "input_modalities": ["image", "text"], "output_schema": ["generated_anim_clips[].job_id/video_url"]},
        {"stage": "finalize_clips", "task": "ffmpeg concat", "input_modalities": ["video"], "output_schema": ["final_video_url"]},
    ]
