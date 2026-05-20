from __future__ import annotations

from typing import Any


def video_model_supported_prompt_modes(profile: dict[str, Any]) -> list[str]:
    caps = profile.get("capabilities") if isinstance(profile.get("capabilities"), dict) else {}
    if bool(profile.get("future_provider")):
        return []
    supports_first = bool(caps.get("first_frame", True))
    supports_last = bool(caps.get("last_frame", True))
    out: list[str] = []
    if supports_first and supports_last:
        out.append("first_last_frame")
    if supports_first:
        out.append("first_frame_only")
    if bool(caps.get("text_only", False)):
        out.append("text_only")
    return out


def video_model_mode_compatible(profile: dict[str, Any], prompt_mode: str) -> tuple[bool, str]:
    mode = (prompt_mode or "first_last_frame").strip() or "first_last_frame"
    supported = video_model_supported_prompt_modes(profile)
    if mode in supported:
        return True, ""
    if bool(profile.get("future_provider")):
        return False, "future provider not implemented"
    if mode == "first_last_frame":
        return False, "model does not support last_frame conditioning"
    if mode == "first_frame_only":
        return False, "model requires a different input contract"
    if mode == "text_only":
        return False, "text_only mode requires text-to-video contract; current i2v models are incompatible"
    return False, f"unsupported prompt_mode={mode}"


def _openrouter_profile(
    model_id: str,
    *,
    first_frame: bool = True,
    last_frame: bool = True,
    durations: list[int] | None = None,
    resolutions: list[str] | None = None,
    refs_level: str = "limited",
    refs_note: str = "",
    degraded: bool = False,
    degraded_reason: str = "",
    text_only: bool = True,
) -> dict[str, Any]:
    # По OpenRouter у большинства video-моделей audio-capability зависит от конкретного endpoint/версии.
    audio_supported = False
    audio_mode = "silent_only"
    audio_note = "В текущем i2v пути звук не генерируется нативно."
    if any(x in model_id for x in ("veo-3.1", "sora-2")):
        audio_mode = "unknown"
        audio_note = "Модель может поддерживать аудио в отдельных режимах, но текущий runtime использует silent i2v."
    return {
        "model_id": model_id,
        "provider": "openrouter",
        "task_type": "image_to_video",
        "backend": "openrouter",
        "input_modalities": ["text", "image"],
        "output_modalities": ["video"],
        "degraded_mode": degraded,
        "degraded_reason": degraded_reason,
        "future_provider": False,
        "capabilities": {
            "first_frame": first_frame,
            "last_frame": last_frame,
            "text_only": bool(text_only),
            "reference_images": False,
            "duration": True,
            "resolution": True,
            "camera_motion": True,
        },
        "limits": {
            "supported_durations": durations or [4, 6, 8],
            "supported_resolutions": resolutions or ["720p", "1080p"],
            "max_prompt_length": 4000,
        },
        "required_fields": ["prompt", "duration", "resolution"],
        "optional_fields": ["last_frame", "camera_motion", "provider", "scene_id", "transition_id"],
        "unsupported_fields_policy": {
            "reference_images": "drop",
            "last_frame": "drop" if not last_frame else "accept",
        },
        "adapter_mapping": {
            "prompt": "prompt",
            "duration": "duration",
            "resolution": "resolution",
            "model": "model",
            "frame_images": "frame_images",
        },
        "adapter": "openrouter_video_adapter",
        "audio_supported": audio_supported,
        "audio_mode": audio_mode,
        "audio_note": audio_note,
        "supported_prompt_modes": (["first_last_frame", "first_frame_only"] if first_frame and last_frame else (["first_frame_only"] if first_frame else [])) + (["text_only"] if text_only else []),
        "refs_quality_level": refs_level,
        "refs_quality_note": refs_note or "Not tested yet",
        "example_request_json": {
            "model": model_id,
            "prompt": "Cinematic motion between keyframes.",
            "duration": 4,
            "resolution": "720p",
            "frame_images": [
                {"type": "image_url", "image_url": {"url": "https://example.org/start.jpg"}, "frame_type": "first_frame"},
            ],
        },
        "example_response_json": {"id": "or-video-id", "polling_url": "https://openrouter.ai/api/v1/videos/xxx"},
    }


def video_model_capability_registry() -> list[dict[str, Any]]:
    return [
        {
            "model_id": "wan2.7-i2v",
            "provider": "dashscope",
            "task_type": "image_to_video",
            "backend": "dashscope",
            "input_modalities": ["image", "text"],
            "output_modalities": ["video"],
            "degraded_mode": False,
            "degraded_reason": "",
            "future_provider": False,
            "capabilities": {
                "first_frame": True,
                "last_frame": True,
                "text_only": False,
                "reference_images": False,
                "duration": True,
                "resolution": True,
                "camera_motion": True,
            },
            "limits": {
                "supported_durations": [2, 3, 4, 5, 6, 8, 10],
                "supported_resolutions": ["480p", "720p", "1080p"],
                "max_prompt_length": 4000,
            },
            "required_fields": ["prompt", "first_frame", "duration", "resolution"],
            "optional_fields": ["last_frame", "camera_motion", "scene_id", "transition_id"],
            "unsupported_fields_policy": {
                "reference_images": "drop",
            },
            "adapter_mapping": {
                "prompt": "prompt",
                "first_frame": "image_url",
                "last_frame": "last_frame_url",
                "duration": "duration",
                "resolution": "resolution",
                "model": "model",
            },
            "adapter": "dashscope_wan_i2v_adapter",
            "audio_supported": False,
            "audio_mode": "silent_only",
            "audio_note": "Текущий dashscope i2v путь в пайплайне без аудио.",
            "supported_prompt_modes": ["first_last_frame", "first_frame_only"],
            "refs_quality_level": "limited",
            "refs_quality_note": "Сцепка first/last frame чувствительна к резким сменам композиции между кадрами.",
            "example_request_json": {
                "model": "wan2.7-i2v",
                "prompt": "Cinematic motion between keyframes.",
                "image_url": "https://example.org/start.jpg",
                "last_frame_url": "https://example.org/end.jpg",
                "duration": 4,
                "resolution": "720p",
            },
            "example_response_json": {"task_id": "wan-task-id", "status": "running"},
        },
        _openrouter_profile("google/veo-3.1", durations=[4, 6, 8], resolutions=["720p", "1080p"], refs_note="High quality, slower generation."),
        _openrouter_profile("google/veo-3.1-fast", durations=[4, 6, 8], resolutions=["720p", "1080p"], refs_note="Faster than Veo 3.1 with balanced quality."),
        _openrouter_profile("google/veo-3.1-lite", durations=[4, 6, 8], resolutions=["720p", "1080p"], refs_note="Budget option; may lose detail in complex scenes."),
        _openrouter_profile("kling/kling-video-o1", durations=[5, 10], resolutions=["720p", "1080p"], refs_note="Strong motion style; continuity can vary."),
        {
            **_openrouter_profile(
                "kwaivgi/kling-v3.0-std",
                durations=[3, 4, 5, 6, 7, 8, 9, 10, 12, 15],
                resolutions=["720x720", "720x1280"],
                refs_note="Stable first-frame video path for test runs.",
            ),
            "reference_payload_mode": "input_references_preferred",
            "preset_contracts": {
                "kling_v3_reference_motion": {
                    "duration": 5,
                    "size": "720x720",
                    "input_references": True,
                    "frame_images_fallback": "first_frame",
                }
            },
        },
        _openrouter_profile("minimax/hailuo-2.3", durations=[5, 10], resolutions=["720p", "1080p"], refs_note="Good motion, less stable identity in fast cuts."),
        _openrouter_profile("bytedance/seedance-2.0", durations=[7, 8], resolutions=["480x480", "720p", "1080p"], refs_note="Good visual richness; sensitive to prompt precision."),
        _openrouter_profile("bytedance/seedance-2.0-fast", durations=[7, 8], resolutions=["480x480", "720p", "1080p"], refs_note="Fast variant with quality trade-offs."),
        _openrouter_profile("bytedance/seedance-1.5-pro", durations=[7, 8], resolutions=["480x480", "720p", "1080p"], refs_note="Older gen; may show more temporal artifacts."),
        _openrouter_profile("alibaba/wan-2.7", durations=[2, 3, 4, 5, 6, 8, 10], resolutions=["480p", "720p", "1080p"], refs_note="Strong i2v baseline, stable first/last frame when scenes are close."),
        _openrouter_profile("alibaba/wan-2.6", durations=[5, 10], resolutions=["720p", "1080p"], refs_note="Older Wan; narrower duration controls."),
        _openrouter_profile("openai/sora-2-pro", durations=[4, 8], resolutions=["720p", "1080p"], first_frame=True, last_frame=False, degraded=True, degraded_reason="last_frame conditioning may be unsupported; using first_frame-only mode.", refs_note="High quality, but first-frame-only conditioning in this pipeline."),
        {
            "model_id": "future/provider-placeholder",
            "provider": "future",
            "task_type": "image_to_video",
            "backend": "future",
            "input_modalities": ["image", "text"],
            "output_modalities": ["video"],
            "degraded_mode": True,
            "degraded_reason": "Future provider skeleton: runtime adapter не подключен.",
            "future_provider": True,
            "capabilities": {
                "first_frame": True,
                "last_frame": True,
                "text_only": False,
                "reference_images": False,
                "duration": True,
                "resolution": True,
                "camera_motion": True,
            },
            "limits": {"supported_durations": [], "supported_resolutions": [], "max_prompt_length": 4000},
            "required_fields": ["prompt", "first_frame"],
            "optional_fields": ["last_frame", "duration", "resolution", "camera_motion"],
            "unsupported_fields_policy": {},
            "adapter_mapping": {},
            "adapter": "future_provider_not_implemented",
            "audio_supported": False,
            "audio_mode": "unknown",
            "audio_note": "Unknown for future provider.",
            "supported_prompt_modes": [],
            "refs_quality_level": "no_data_yet",
            "refs_quality_note": "Not tested yet",
            "example_request_json": {},
            "example_response_json": {},
        },
    ]


def get_video_model_profile(model_id: str) -> dict[str, Any] | None:
    mid = (model_id or "").strip()
    for row in video_model_capability_registry():
        if str(row.get("model_id") or "").strip() == mid:
            return row
    return None


def openrouter_video_models_catalog() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in video_model_capability_registry():
        if str(row.get("provider") or "").strip() != "openrouter":
            continue
        out.append(
            {
                "model_id": str(row.get("model_id") or ""),
                "task_type": str(row.get("task_type") or ""),
                "required_fields": list(row.get("required_fields") or []),
                "optional_fields": list(row.get("optional_fields") or []),
                "limits": dict(row.get("limits") or {}),
                "audio_supported": bool(row.get("audio_supported")),
                "audio_mode": str(row.get("audio_mode") or "unknown"),
                "audio_note": str(row.get("audio_note") or ""),
            }
        )
    return out


def build_provider_request_from_internal_video_payload(
    *,
    internal_payload: dict[str, Any],
    model_profile: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(internal_payload or {})
    caps = model_profile.get("capabilities") if isinstance(model_profile.get("capabilities"), dict) else {}
    limits = model_profile.get("limits") if isinstance(model_profile.get("limits"), dict) else {}
    required = set(model_profile.get("required_fields") or [])
    backend = str(model_profile.get("backend") or model_profile.get("provider") or "").strip()
    model_id = str(model_profile.get("model_id") or "").strip()

    accepted: list[str] = []
    dropped: list[str] = []
    inlined: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    if bool(model_profile.get("future_provider")):
        errors.append("provider adapter not implemented yet")

    prompt = str(payload.get("prompt") or "").strip()
    first_frame = str(payload.get("first_frame") or payload.get("image_url") or "").strip()
    last_frame = str(payload.get("last_frame") or payload.get("last_frame_url") or "").strip()
    prompt_mode = str(payload.get("prompt_mode") or "first_last_frame").strip() or "first_last_frame"
    duration = int(payload.get("duration") or 4)
    resolution = str(payload.get("resolution") or "720p").strip()
    size = str(payload.get("size") or "").strip()
    reference_image_url = str(payload.get("reference_image_url") or "").strip()
    use_input_references = bool(payload.get("use_input_references"))

    supports_first = bool(caps.get("first_frame", True))
    supports_last = bool(caps.get("last_frame", True))

    if prompt:
        accepted.append("prompt")
    if first_frame and supports_first:
        accepted.append("first_frame")
    if last_frame and supports_last:
        accepted.append("last_frame")
    if prompt_mode not in {"first_frame_only", "text_only", "first_last_frame"}:
        errors.append(f"unsupported prompt_mode={prompt_mode}")
    elif prompt_mode == "first_frame_only":
        if last_frame:
            dropped.append("last_frame")
            warnings.append("prompt_mode=first_frame_only: last_frame dropped")
        last_frame = ""
    elif prompt_mode == "text_only":
        if first_frame:
            dropped.append("first_frame")
            warnings.append("prompt_mode=text_only: first_frame dropped")
        if last_frame:
            dropped.append("last_frame")
            warnings.append("prompt_mode=text_only: last_frame dropped")
        first_frame = ""
        last_frame = ""

    if first_frame and not supports_first:
        dropped.append("first_frame")
        warnings.append("first_frame unsupported by selected model")
    if last_frame and not supports_last:
        dropped.append("last_frame")
        warnings.append("last_frame unsupported by selected model")

    allowed_durations = list(limits.get("supported_durations") or [])
    if allowed_durations and duration not in allowed_durations:
        errors.append(f"duration={duration} not supported: {allowed_durations}")
    allowed_res = list(limits.get("supported_resolutions") or [])
    if allowed_res and resolution not in allowed_res:
        errors.append(f"resolution={resolution} not supported: {allowed_res}")

    max_prompt_len = int(limits.get("max_prompt_length") or 0)
    if max_prompt_len > 0 and len(prompt) > max_prompt_len:
        errors.append(f"prompt too long: {len(prompt)} > {max_prompt_len}")

    missing_required = []
    for fld in required:
        v = payload.get(fld)
        if fld == "first_frame":
            v = first_frame
            if prompt_mode == "text_only":
                continue
        if fld == "prompt":
            v = prompt
        if v in (None, "", []):
            missing_required.append(fld)
    if missing_required:
        errors.append(f"required fields missing: {', '.join(missing_required)}")

    provider_request: dict[str, Any] = {}
    if backend == "openrouter":
        provider_request = {
            "model": model_id,
            "prompt": prompt,
            "duration": duration,
        }
        if size:
            provider_request["size"] = size
        else:
            provider_request["resolution"] = resolution
        frame_images: list[dict[str, Any]] = []
        if first_frame and supports_first:
            frame_images.append({"type": "image_url", "image_url": {"url": first_frame}, "frame_type": "first_frame"})
        if last_frame and supports_last:
            frame_images.append({"type": "image_url", "image_url": {"url": last_frame}, "frame_type": "last_frame"})
        if use_input_references and reference_image_url:
            provider_request["input_references"] = [
                {"type": "image_url", "image_url": reference_image_url}
            ]
            accepted.append("input_references")
        elif frame_images:
            provider_request["frame_images"] = frame_images
    elif backend == "dashscope":
        provider_request = {
            "model": model_id,
            "prompt": prompt,
            "image_url": first_frame if supports_first else None,
            "last_frame_url": (last_frame or None) if supports_last else None,
            "duration": duration,
            "resolution": resolution,
        }
    else:
        provider_request = {
            "model": model_id,
            "prompt": prompt,
            "first_frame": first_frame,
            "last_frame": last_frame or None,
            "duration": duration,
            "resolution": resolution,
        }
        warnings.append("provider request is placeholder for future adapter")

    for fld, cap_name in (("camera_motion", "camera_motion"), ("reference_images", "reference_images")):
        val = payload.get(fld)
        if val in (None, "", []):
            continue
        if bool(caps.get(cap_name)):
            accepted.append(fld)
        else:
            dropped.append(fld)
            warnings.append(f"{fld} unsupported by selected model")

    status = "blocked" if errors else ("degraded" if warnings or bool(model_profile.get("degraded_mode")) else "full")
    return {
        "internal_payload": payload,
        "prompt_mode": prompt_mode,
        "model_profile": model_profile,
        "resolved_capabilities": caps,
        "provider_request": provider_request,
        "accepted_fields": accepted,
        "dropped_fields": dropped,
        "inlined_fields": inlined,
        "missing_required_fields": missing_required,
        "warnings": warnings,
        "errors": errors,
        "status": status,
        "degraded_reason": str(model_profile.get("degraded_reason") or ""),
        "ok": not errors,
    }

