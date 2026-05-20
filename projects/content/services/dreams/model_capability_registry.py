from __future__ import annotations

from typing import Any

from services.images.openrouter_image_models_catalog import (
    OPENROUTER_IMAGE_MODELS_CATALOG,
    openrouter_model_supports_image_and_text_output,
    openrouter_model_supports_reference_images,
)


def _openrouter_profile_for_model(model_id: str) -> dict[str, Any]:
    mid = (model_id or "").strip()
    low = mid.lower()
    is_flux = "flux" in low
    is_seedream = "seedream" in low
    is_flux_like = is_flux or is_seedream
    is_gpt5 = "gpt-5" in low
    is_gemini = "gemini" in low
    is_qwen = "qwen" in low
    supports_image_text_output = openrouter_model_supports_image_and_text_output(mid)
    supports_refs = openrouter_model_supports_reference_images(mid)
    max_refs = 4 if is_flux_like else (6 if is_gpt5 else 8)
    supported_res = ["1K", "2K"]
    if "gemini-3" in low or is_gemini:
        supported_res = ["0.5K", "1K", "2K", "4K"]
    if is_qwen:
        supported_res = ["1K"]
    degraded_reason = ""
    refs_quality_level = ""
    refs_quality_note = ""
    if is_seedream:
        degraded_reason = (
            "Seedream 4.5 работает в degraded mode: previous_frame и служебные refs "
            "инлайнятся в prompt, часть control-полей недоступна нативно."
        )
        refs_quality_level = "degraded"
        refs_quality_note = "Референсы применяются нестабильно; композиция персонажа может заметно дрейфовать между кадрами."
    elif is_flux:
        degraded_reason = "Flux имеет ограниченный набор control-полей, refs и continuity частично деградируют."
        refs_quality_level = "limited"
        refs_quality_note = "Качество связи с персонажными референсами ограничено; лучше использовать короткие цепочки и строгий prompt."
    elif "gemini-2.5-flash-image" in low:
        refs_quality_level = "limited"
        refs_quality_note = "По тестам: персонажный референс не всегда стабильно встраивается в кадр; возможен дрейф позы/масштаба."
    elif "gemini-3.1-flash-image-preview" in low:
        refs_quality_level = "limited"
        refs_quality_note = "По тестам: качество refs лучше в простых сценах, но в сложной композиции персонаж может частично терять идентичность."

    return {
        "model_id": mid,
        "provider": "openrouter",
        "task_type": "text_to_image",
        "input_modalities": ["text", "image"],
        "output_modalities": ["image", "text"] if supports_image_text_output else ["image"],
        "degraded_mode": bool(degraded_reason),
        "degraded_reason": degraded_reason,
        "refs_quality_level": refs_quality_level,
        "refs_quality_note": refs_quality_note,
        "capabilities": {
            "first_frame": False,
            "last_frame": False,
            "reference_images": bool(supports_refs),
            "character_reference": bool(supports_refs),
            "style_reference": False,
            "environment_reference": bool(supports_refs),
            "aspect_ratio": True,
            "duration": False,
            "resolution": True,
            "seed": bool(is_flux_like),
            "negative_prompt": not is_qwen,
            "camera_motion": False,
            "supports_image_text_output": bool(supports_image_text_output),
            "previous_frame": False,
        },
        "limits": {
            "max_reference_images": max_refs,
            "recommended_reference_images": 3,
            "max_prompt_length": 8000,
            "supported_aspect_ratios": ["1:1", "9:16", "16:9", "4:3"],
            "supported_durations": [],
            "supported_resolutions": supported_res,
            "max_file_size": 20_000_000,
            "supported_file_types": ["jpg", "jpeg", "png", "webp"],
        },
        "required_fields": ["prompt"],
        "optional_fields": ["reference_images", "aspect_ratio", "resolution", "negative_prompt", "seed"],
        "unsupported_fields_policy": {
            "previous_frame_reference": "inline_prompt",
            "character_references": "inline_prompt" if (is_flux_like or is_qwen) else "drop",
            "environment_references": "inline_prompt" if (is_flux_like or is_qwen) else "drop",
            "style_references": "drop",
            "camera_motion": "inline_prompt",
            "last_frame": "drop",
            "first_frame": "drop",
        },
        "adapter_mapping": {
            "prompt": "prompt",
            "reference_images": "reference_image_urls",
            "aspect_ratio": "aspect_ratio",
            "resolution": "image_size",
            "negative_prompt": "negative_prompt",
            "seed": "seed",
            "output_modalities": ["image", "text"] if supports_image_text_output else ["image"],
            "input_modalities": ["text", "image"],
        },
        "adapter": "openrouter_image_adapter",
    }


def model_capability_registry() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in OPENROUTER_IMAGE_MODELS_CATALOG:
        mid = str(row.get("id") or "").strip()
        if not mid:
            continue
        prof = _openrouter_profile_for_model(mid)
        prof["example_request_json"] = {
            "prompt": "cinematic penguin dream scene",
            "reference_images": ["https://example.org/ref1.png"],
            "aspect_ratio": "9:16",
            "resolution": "1K",
        }
        prof["example_response_json"] = {"image_urls": ["https://example.org/out.png"], "usage": {"total_tokens": 1234}}
        rows.append(prof)
    return rows


def get_model_profile(model_id: str) -> dict[str, Any] | None:
    mid = (model_id or "").strip()
    for row in model_capability_registry():
        if str(row.get("model_id") or "").strip() == mid:
            return row
    return None


def build_provider_request_from_internal_payload(
    *,
    internal_payload: dict[str, Any],
    model_profile: dict[str, Any],
) -> dict[str, Any]:
    caps = model_profile.get("capabilities") if isinstance(model_profile.get("capabilities"), dict) else {}
    limits = model_profile.get("limits") if isinstance(model_profile.get("limits"), dict) else {}
    required = set(model_profile.get("required_fields") or [])
    mapping = model_profile.get("adapter_mapping") if isinstance(model_profile.get("adapter_mapping"), dict) else {}
    unsupported_policy = model_profile.get("unsupported_fields_policy") if isinstance(model_profile.get("unsupported_fields_policy"), dict) else {}

    payload = dict(internal_payload or {})
    prompt = str(payload.get("prompt") or "").strip()
    provider_req: dict[str, Any] = {"model": model_profile.get("model_id")}
    accepted: list[str] = []
    dropped: list[str] = []
    inlined: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    refs = [str(x).strip() for x in (payload.get("reference_images") or []) if str(x).strip()]
    max_refs = int(limits.get("max_reference_images") or 0)
    if max_refs >= 0 and len(refs) > max_refs:
        errors.append(f"reference_images превышают лимит: {len(refs)} > {max_refs}")
    required_ref_slots = list(payload.get("required_reference_slots") or [])
    refs_required = bool(required_ref_slots)
    if refs_required and refs and not bool(caps.get("reference_images")):
        errors.append("модель не поддерживает reference_images при обязательных refs для кадра")

    missing_slots = list(payload.get("missing_required_references") or [])
    if missing_slots:
        warnings.append(
            "missing required references (runtime data): "
            + ", ".join(str(x) for x in missing_slots)
        )

    if prompt:
        provider_req[str(mapping.get("prompt") or "prompt")] = prompt
        accepted.append("prompt")
    for fld, cap_name in (
        ("reference_images", "reference_images"),
        ("aspect_ratio", "aspect_ratio"),
        ("resolution", "resolution"),
        ("negative_prompt", "negative_prompt"),
        ("seed", "seed"),
    ):
        val = payload.get(fld)
        if fld == "reference_images":
            val = refs
        if val in (None, "", []):
            continue
        if not bool(caps.get(cap_name)):
            dropped.append(fld)
            continue
        provider_req[str(mapping.get(fld) or fld)] = val
        accepted.append(fld)

    # character/environment/style refs are internal planning metadata.
    # Final provider request already receives resolved URLs in `reference_images`,
    # so do not surface noisy per-model warnings for these metadata fields.
    for fld in ("camera_motion", "first_frame", "last_frame"):
        val = payload.get(fld)
        if val in (None, "", []):
            continue
        pol = str(unsupported_policy.get(fld) or "drop")
        if pol == "inline_prompt":
            addon = f"{fld}={val}"
            provider_req[str(mapping.get("prompt") or "prompt")] = (
                str(provider_req.get(str(mapping.get("prompt") or "prompt")) or "").strip() + f"\n{addon}"
            ).strip()
            inlined.append(fld)
            warnings.append(f"{fld} не поддерживается нативно: инлайн в prompt")
        elif pol == "error":
            errors.append(f"{fld} не поддерживается выбранной моделью")
        else:
            dropped.append(fld)
            warnings.append(f"{fld} не поддерживается выбранной моделью: поле отброшено")

    prev_ref = str(payload.get("previous_frame_reference") or "").strip()
    if prev_ref:
        pol = str(unsupported_policy.get("previous_frame_reference") or "drop")
        if pol == "inline_prompt":
            provider_req[str(mapping.get("prompt") or "prompt")] = (
                str(provider_req.get(str(mapping.get("prompt") or "prompt")) or "").strip()
                + f"\nReference continuity: previous_frame={prev_ref}"
            ).strip()
            inlined.append("previous_frame_reference")
            warnings.append("previous_frame не поддерживается нативно: инлайн в prompt")
        else:
            dropped.append("previous_frame_reference")
            warnings.append("previous_frame не поддерживается нативно: поле отброшено")

    max_prompt_len = int(limits.get("max_prompt_length") or 0)
    final_prompt = str(provider_req.get(str(mapping.get("prompt") or "prompt")) or "")
    if max_prompt_len > 0 and len(final_prompt) > max_prompt_len:
        errors.append(f"prompt слишком длинный: {len(final_prompt)} > {max_prompt_len}")

    ar = str(payload.get("aspect_ratio") or "").strip()
    if ar:
        allowed_ar = list(limits.get("supported_aspect_ratios") or [])
        if allowed_ar and ar not in allowed_ar:
            errors.append(f"aspect_ratio={ar} не поддерживается: {allowed_ar}")

    res = str(payload.get("resolution") or "").strip()
    if res:
        allowed_res = list(limits.get("supported_resolutions") or [])
        if allowed_res and res not in allowed_res:
            errors.append(f"resolution={res} не поддерживается: {allowed_res}")

    missing_required = [x for x in required if not payload.get(x)]
    if missing_required:
        errors.append(f"required fields missing: {', '.join(missing_required)}")

    provider_req["output_modalities"] = list(mapping.get("output_modalities") or ["image"])
    provider_req["input_modalities"] = list(mapping.get("input_modalities") or ["text", "image"])
    status = "blocked" if errors else ("degraded" if warnings else "full")

    return {
        "internal_payload": payload,
        "model_profile": model_profile,
        "resolved_capabilities": caps,
        "provider_request": provider_req,
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
