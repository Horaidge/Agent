"""
Пошаговый воркер Dream Pipeline Lite: каждый вызов выполняет ровно одну атомарную операцию.

Состояние читается и пишется в Mongo по (user_id, lite_run_id) — без общей памяти между пользователями.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import re
import time
from pathlib import Path
from typing import Any

from core.config.settings import get_settings
from storage.dream_lite_asset_repository import DreamLiteAssetRepository
from storage.dream_lite_run_repository import DreamLiteRunRepository
from storage.dream_lite_summary_repository import DreamLiteSummaryRepository
from services.dreams.video_model_capability_registry import get_video_model_profile

from services.observability.dream_pipeline_lite import (
    LITE_STEP2_RUNTIME_ENTRYPOINT,
    LITE_OPENROUTER_IMAGE_ASPECT_RATIO,
    LITE_OPENROUTER_IMAGE_SIZE,
    build_lite_frame_image_prompt,
    collect_lite_frame_reference_urls,
    lite_ref_slots_canonical_for_ui,
    lite_refs_summary_for_ui,
    lite_chat_text,
    lite_materialize_url_list_for_mongo,
    lite_resolve_image_url_for_external_api,
    lite_collect_animate_i2v_segments,
    lite_default_transition_plan,
    lite_transition_plan_with_selection,
    lite_ref_urls_for_ui,
    lite_resolve_use_previous_frame,
    lite_effective_prompt_mode,
    lite_environments_system_prompt,
    lite_environments_user_message,
    resolve_lite_env_url,
    lite_build_transition_system_prompt,
    lite_resolve_montage_preset,
    lite_run_step2_frames_with_prev_link,
    lite_transitions_kling_reference_system_prompt,
    lite_transitions_seedance_system_prompt,
    lite_transitions_system_prompt,
    lite_transitions_wan26_system_prompt,
    lite_transitions_user_message,
    parse_lite_transition_plan_from_model_text,
    split_lite_step1_world,
)
from services.observability.dream_lite_metrics_store import record_metric
from services.tools.openrouter_image_tools import tool_generate_image_openrouter
from services.tools.video_tools import get_video_job_service, tool_image_to_video
from services.video.final_video_assembler import FinalVideoAssemblerError, assemble_remote_mp4s
from services.video.openrouter_video_client import normalize_openrouter_video_model_id

logger = logging.getLogger(__name__)


def _compact_ref_slots_for_mongo(ref_slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Не храним в Mongo inline data URI из ref_slots.url, иначе документ run быстро
    превышает лимит 16MB на длинных прогонах.
    """
    out: list[dict[str, Any]] = []
    for slot in list(ref_slots or []):
        if not isinstance(slot, dict):
            continue
        s = dict(slot)
        u = str(s.get("url") or "").strip()
        if u.startswith("data:") or len(u) > 500:
            s["url"] = ""
        out.append(s)
    return out


def _resolve_i2v_input_url(raw_url: str | None) -> str | None:
    """
    Для WAN/DashScope нужны внешние URL.
    Если кадр хранится как /dev/static/... — разворачиваем в PUBLIC_BASE_URL + path.
    """
    u = str(raw_url or "").strip()
    if not u:
        return None
    if u.startswith("/dev/static/"):
        embedded = lite_resolve_image_url_for_external_api(u)
        if embedded and embedded != u:
            return embedded
        base = (get_settings().public_base_url or "").strip().rstrip("/")
        if base:
            return f"{base}{u}"
        # Нельзя отдавать провайдеру относительный /dev/static путь.
        return None
    # fallback: существующее поведение для абсолютных URL/data URI
    return lite_resolve_image_url_for_external_api(u) or u


def _normalize_provider_duration_sec(
    calculated_sec: int,
    *,
    backend: str,
    openrouter_model: str | None,
    supported_durations: list[int],
) -> int:
    d = max(1, int(calculated_sec))
    b = str(backend or "").strip().lower()
    or_model = normalize_openrouter_video_model_id(openrouter_model or "")
    if b == "openrouter" and or_model == "alibaba/wan-2.6":
        return 5
    if supported_durations:
        allowed = [x for x in supported_durations if x <= 6]
        if allowed:
            return min(allowed, key=lambda x: abs(x - d))
        return min(supported_durations)
    return max(1, min(d, 6))


def _is_first_frame_stable_model(model_id: str) -> bool:
    mid = normalize_openrouter_video_model_id(model_id or "")
    return mid in {"kwaivgi/kling-v3.0-std"}


def _sync_gen_env_image(
    title: str,
    body: str,
    *,
    model: str | None = None,
    simple_mode: bool = False,
) -> dict[str, Any]:
    prompt = (
        (
            "Environment plate for storyboard (simple mode): clean location-only scene, no living beings. "
            "Strictly no humans, animals, birds, insects, crowds, silhouettes, distant people, or biological creatures. "
            "Focus on architecture/landscape, materials, light, weather, color palette, and clear action zone. "
        )
        if simple_mode
        else (
            "Environment plate for storyboard: prefer human eye level, foreground and a clear focal zone for action; "
            "avoid empty abstract panorama unless the brief explicitly demands vast distance or panorama scale. "
        )
    ) + f"{body}\nSingle coherent frame, high detail, coherent lighting, no text, no watermark."
    tool_res = tool_generate_image_openrouter(
        prompt,
        aspect_ratio=LITE_OPENROUTER_IMAGE_ASPECT_RATIO,
        image_size=LITE_OPENROUTER_IMAGE_SIZE,
        model=(model or "").strip() or None,
        strict_model=bool((model or "").strip()),
    )
    return tool_res.to_dict()


def _sync_gen_char_image(
    title: str,
    body: str,
    *,
    env_context: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    prompt = (
        "Isolated human casting reference / model sheet: exactly one adult or clearly aged person, full figure or three-quarter, "
        "neutral relaxed stance, soft studio or plain background. "
        "Default casting requirement: European appearance. "
        "Face must be clearly visible, near-frontal, sharp focus, no occlusion. "
        "Outfit policy: if environment implies climate/location constraints, choose practical matching clothing; "
        "if casting notes explicitly require otherwise, casting notes have higher priority. "
        "Do not show interactions, second people, animals, crowds, or story action — even if the text below mentions them; "
        "render only this person's standalone appearance. "
        f"Environment context (for outfit only): {env_context}\n"
        f"Casting notes: {body}\n"
        "Readable face and silhouette, no text, no watermark, no non-human creature as subject."
    )
    tool_res = tool_generate_image_openrouter(
        prompt,
        aspect_ratio=LITE_OPENROUTER_IMAGE_ASPECT_RATIO,
        image_size=LITE_OPENROUTER_IMAGE_SIZE,
        model=(model or "").strip() or None,
        strict_model=bool((model or "").strip()),
    )
    return tool_res.to_dict()


def _sync_gen_frame_image(img_prompt: str, ref_urls: list[str], *, model: str | None = None) -> dict[str, Any]:
    tool_res = tool_generate_image_openrouter(
        img_prompt.strip(),
        reference_image_urls=ref_urls if ref_urls else None,
        aspect_ratio=LITE_OPENROUTER_IMAGE_ASPECT_RATIO,
        image_size=LITE_OPENROUTER_IMAGE_SIZE,
        model=(model or "").strip() or None,
        strict_model=bool((model or "").strip()),
    )
    return tool_res.to_dict()


def _short_ref_urls(urls: list[str], *, max_items: int = 3) -> list[str]:
    out: list[str] = []
    for u in list(urls or [])[:max_items]:
        s = str(u or "").strip()
        if not s:
            continue
        out.append(s if len(s) <= 80 else f"{s[:64]}...{s[-12:]}")
    return out


def _ref_text_risk_slots(ref_slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for s in list(ref_slots or []):
        if not isinstance(s, dict):
            continue
        det = str(s.get("detail") or "").strip().lower()
        lbl = str(s.get("label") or "").strip().lower()
        blob = f"{det} {lbl}"
        if any(x in blob for x in ("text", "subtitle", "sign", "logo", "caption", "letter")):
            flags.append(
                {
                    "role": str(s.get("role") or ""),
                    "detail": str(s.get("detail") or "")[:120],
                }
            )
    return flags


def _simple_labels_from_ref_slots(ref_slots: list[dict[str, Any]]) -> tuple[str, str]:
    env_label = ""
    dreamer_label = ""
    for s in ref_slots:
        role = str(s.get("role") or "")
        detail = str(s.get("detail") or "").strip()
        if role in {"environment", "extra_environment"} and not env_label:
            env_label = detail
        if role in {"dreamer", "character"} and not dreamer_label:
            dreamer_label = detail
    return env_label, dreamer_label


def _resolve_ref_urls_for_external_api(urls: list[str]) -> list[str]:
    out: list[str] = []
    for u in list(urls or []):
        raw = str(u or "").strip()
        if not raw:
            continue
        resolved = lite_resolve_image_url_for_external_api(raw) or raw
        if resolved and resolved not in out:
            out.append(resolved)
    return out


def _is_dreamer_text(blob: str) -> bool:
    t = re.sub(r"[^a-zа-яё0-9_]+", " ", str(blob or "").lower(), flags=re.IGNORECASE).strip()
    if not t:
        return False
    return (
        t == "dreamer"
        or t.startswith("dreamer_")
        or "dreamer" in t
        or "protagonist" in t
        or "главный персонаж" in t
        or "главная героиня" in t
        or "главный герой" in t
    )


def _is_dreamer_title(title: str) -> bool:
    return _is_dreamer_text(title)


def _sync_lite_i2v_segment(
    seg: dict[str, Any],
    *,
    owner_key: str,
    lite_run_id: str,
    segment_index: int,
    i2v_model: str = "wan2.7-i2v",
    duration_sec: int = 4,
    resolution: str = "720p",
    video_backend: str | None = None,
    openrouter_model: str | None = None,
) -> dict[str, Any]:
    prompt = str(seg.get("final_prompt") or "").strip()
    if not prompt:
        prompt = (
            "Cinematic motion between storyboard keyframes, same characters and space, coherent light. "
            f"{seg.get('motion_prompt') or ''}\n"
            "No text or subtitles on screen."
        ).strip()
    image_url = _resolve_i2v_input_url(seg.get("image_url"))
    last_frame_url = _resolve_i2v_input_url(seg.get("last_frame_url"))
    seg_mode = (
        str(seg.get("effective_prompt_mode") or "").strip()
        or str(seg.get("prompt_mode") or "").strip()
        or "first_last_frame"
    )
    if not image_url and seg_mode != "text_only":
        return {"ok": False, "status": "failed", "error": "missing_image_url_for_i2v"}
    request_ts = time.time()
    out = tool_image_to_video(
        prompt=prompt,
        image_url=image_url or "",
        duration=max(1, int(duration_sec)),
        resolution=(resolution or "720p").strip() or "720p",
        owner_user_id=owner_key,
        model=(i2v_model or "wan2.7-i2v").strip() or "wan2.7-i2v",
        last_frame_url=last_frame_url,
        video_backend=(video_backend or "").strip() or None,
        openrouter_model=(openrouter_model or "").strip() or None,
        job_extra={
            "dream_lite_run_id": lite_run_id,
            "dream_lite_segment_index": segment_index,
            "montage_preset": str(seg.get("montage_preset") or "default"),
            "reference_image_url": str(
                (seg.get("api_payload_preview") or {}).get("reference_image_url")
                if isinstance(seg.get("api_payload_preview"), dict)
                else (seg.get("reference_image_url") or seg.get("image_url") or "")
            ),
            "dev_relaxed_validation": bool(
                str(image_url or "").startswith("data:")
                or str(image_url or "").startswith("/dev/static/")
            ),
        },
    )
    first_response_ts = time.time()
    out["request_at"] = request_ts
    out["first_response_at"] = first_response_ts
    out["completed_at"] = first_response_ts
    out["duration_ms"] = int((first_response_ts - request_ts) * 1000)
    out["provider_latency_ms"] = int((first_response_ts - request_ts) * 1000)
    out["requested_model"] = (openrouter_model or i2v_model or "").strip()
    out["effective_model"] = (openrouter_model or i2v_model or "").strip()
    out["video_backend"] = (video_backend or get_settings().video_generation_backend or "dashscope")
    return out


def _urls_from_slots(generated: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for title, slot in (generated or {}).items():
        if not isinstance(slot, dict):
            continue
        if slot.get("ok") and slot.get("urls"):
            urls = list(slot.get("urls") or [])
            if urls:
                out[str(title)] = str(urls[0])
    return out


def _resolved_urls_from_slots(generated: dict[str, Any]) -> dict[str, str]:
    """Пути из Mongo (/dev/static/...) → data URI для OpenRouter."""
    out: dict[str, str] = {}
    for title, u0 in _urls_from_slots(generated).items():
        resolved = lite_resolve_image_url_for_external_api(u0)
        if resolved:
            out[title] = resolved
    return out


def _dream_lite_final_video_dir() -> Path:
    d = Path(__file__).resolve().parent.parent.parent / "ui" / "dev" / "static" / "dream_lite_final"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_lite_run_filename_part(lite_run_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (lite_run_id or "").strip())
    return s[:120] if s else "run"


def _sync_finalize_lite_clips(
    doc: dict[str, Any],
    *,
    user_id: int,
    lite_run_id: str,
) -> dict[str, Any]:
    """Дождаться готовности i2v job, склеить mp4 в ui/dev/static/dream_lite_final/."""
    clips = list(doc.get("generated_anim_clips") or [])
    svc = get_video_job_service()
    updated: list[dict[str, Any]] = []
    urls: list[str] = []
    failed_transitions: list[dict[str, Any]] = []
    for c in sorted(clips, key=lambda x: int(x.get("segment_index") if x.get("segment_index") is not None else 0)):
        c = dict(c)
        jid = c.get("job_id")
        vu = (str(c.get("video_url") or "").strip())
        if vu:
            urls.append(vu)
            updated.append(c)
            continue
        if not jid:
            failed_transitions.append(
                {
                    "segment_index": c.get("segment_index"),
                    "from_frame_index": c.get("from_frame_index"),
                    "to_frame_index": c.get("to_frame_index"),
                    "reason": "missing_job_id",
                }
            )
            updated.append(c)
            continue
        try:
            job = svc.poll_job_until_done(str(jid), timeout_sec=2400.0, interval_sec=3.0)
        except TimeoutError:
            c["status"] = "timeout"
            c["error"] = "Таймаут ожидания video job"
            failed_transitions.append(
                {
                    "segment_index": c.get("segment_index"),
                    "from_frame_index": c.get("from_frame_index"),
                    "to_frame_index": c.get("to_frame_index"),
                    "reason": c["error"],
                }
            )
            updated.append(c)
            continue
        c["status"] = job.get("status")
        c["video_url"] = job.get("video_url")
        done_ts = time.time()
        c["completed_at"] = done_ts
        if c.get("request_at"):
            try:
                c["duration_ms"] = int((done_ts - float(c.get("request_at"))) * 1000)
            except Exception:
                pass
        if job.get("error"):
            c["error"] = job.get("error")
        if job.get("status") != "succeeded":
            failed_transitions.append(
                {
                    "segment_index": c.get("segment_index"),
                    "from_frame_index": c.get("from_frame_index"),
                    "to_frame_index": c.get("to_frame_index"),
                    "reason": c.get("error") or f"video_job_status:{c.get('status')}",
                }
            )
        updated.append(c)
        if job.get("status") == "succeeded" and job.get("video_url"):
            u = str(job["video_url"]).strip()
            if u:
                urls.append(u)

    base = f"{int(user_id)}_{_safe_lite_run_filename_part(lite_run_id)}.mp4"
    out_path = _dream_lite_final_video_dir() / base
    public_url = f"/dev/static/dream_lite_final/{base}"

    if not urls:
        return {
            "generated_anim_clips": updated,
            "failed_transitions": failed_transitions,
            "final_video_url": None,
            "final_assembly_error": "Нет готовых видео URL (нет animate_transition или все i2v провалились).",
            "step_phase": "completed",
            "run_status": "failed",
            "last_error": "Нет готовых видео URL для сборки финального ролика.",
        }

    try:
        assemble_remote_mp4s(urls, out_path)
    except FinalVideoAssemblerError as exc:
        logger.warning("dream_lite finalize: склейка не удалась: %s", exc)
        return {
            "generated_anim_clips": updated,
            "failed_transitions": failed_transitions,
            "final_video_url": None,
            "final_assembly_error": str(exc),
            "step_phase": "completed",
            "run_status": "failed",
            "last_error": str(exc),
        }

    return {
        "generated_anim_clips": updated,
        "failed_transitions": failed_transitions,
        "final_video_url": public_url,
        "final_assembly_error": None,
        "step_phase": "completed",
        "run_status": "completed",
        "last_error": None,
    }


async def process_dream_lite_run_step(
    *,
    repo: DreamLiteRunRepository,
    openai: Any,
    user_id: int,
    lite_run_id: str,
    summary_repo: DreamLiteSummaryRepository | None = None,
    asset_repo: DreamLiteAssetRepository | None = None,
) -> dict[str, Any]:
    def _s(v: Any, cap: int = 280) -> str:
        s = str(v or "").strip()
        return s if len(s) <= cap else s[:cap] + "…"

    doc = await repo.get_run(user_id=user_id, lite_run_id=lite_run_id)
    if not doc:
        return {"ok": False, "error": "run_not_found"}
    state_doc = dict(doc)
    owner_user_id = int(user_id)
    owner_run_id = str(lite_run_id or "").strip()

    async def _sync_projections(run_doc: dict[str, Any]) -> None:
        if not isinstance(run_doc, dict):
            return
        try:
            if summary_repo is not None:
                await summary_repo.upsert_from_run_doc(run_doc)
            if asset_repo is not None:
                await asset_repo.upsert_from_run_doc(run_doc)
        except Exception:
            logger.warning("dream_lite projections sync failed", exc_info=True)

    async def _update_run(
        patch: dict[str, Any],
        *,
        user_id: int | None = None,
        lite_run_id: str | None = None,
    ) -> bool:
        nonlocal state_doc
        p = dict(patch or {})
        prev_phase = str((state_doc or {}).get("step_phase") or "")
        next_phase = str(p.get("step_phase") or prev_phase)
        if next_phase and next_phase != prev_phase:
            rev = int((state_doc or {}).get("phase_revision") or 0) + 1
            p["phase_revision"] = rev
            p["step_id"] = f"{next_phase}:{rev}"
        if "generated_frames" in p:
            p["has_frames"] = bool(list(p.get("generated_frames") or []))
        if p.get("final_video_url"):
            p["has_final_video"] = True
        if str(p.get("step_phase") or "").strip() == "completed":
            p.setdefault("completed_at", datetime.now(timezone.utc))
        uid_eff = owner_user_id if user_id is None else int(user_id)
        rid_eff = owner_run_id if lite_run_id is None else str(lite_run_id or "").strip()
        ok = await repo.update_run(
            user_id=uid_eff,
            lite_run_id=rid_eff,
            patch=p,
        )
        fresh = await repo.get_run(user_id=uid_eff, lite_run_id=rid_eff)
        if isinstance(fresh, dict):
            state_doc = fresh
            await _sync_projections(fresh)
        return ok

    async def _trace(event_type: str, **fields: Any) -> None:
        try:
            payload = {"event": event_type}
            payload.update(fields)
            await repo.append_execution_trace(
                user_id=user_id,
                lite_run_id=lite_run_id,
                event=payload,
            )
        except Exception:
            logger.debug("dream_lite trace append failed", exc_info=True)

    async def _fail_run(error: str, *, step: str | None = None) -> dict[str, Any]:
        msg = str(error or "unknown_error")
        await _trace("run_failed", step=step or "", error=_s(msg))
        await _update_run(
            user_id=user_id,
            lite_run_id=lite_run_id,
            patch={
                "run_status": "failed",
                "step_phase": "failed",
                "last_error": msg,
            },
        )
        out: dict[str, Any] = {"ok": False, "error": msg}
        if step:
            out["step"] = step
        return out

    # Run до добавления этапа transition_plan: докрутить план без новой генерации кадров.
    if (
        doc.get("step_phase") == "completed"
        and doc.get("run_status") == "completed"
        and doc.get("transition_plan") is None
        and (doc.get("generated_frames") or [])
    ):
        await _update_run(patch={"step_phase": "transition_plan", "run_status": "active"})
        doc = await repo.get_run(user_id=user_id, lite_run_id=lite_run_id) or doc

    # Старые run: были completed до шага i2v — докрутить очередь анимации.
    if (
        doc.get("run_status") == "completed"
        and doc.get("step_phase") == "completed"
        and doc.get("transition_plan")
        and not doc.get("anim_run_complete")
    ):
        await _update_run(
            user_id=user_id,
            lite_run_id=lite_run_id,
            patch={
                "step_phase": "anim_i2v",
                "gen_anim_i": int(doc.get("gen_anim_i") or 0),
                "generated_anim_clips": list(doc.get("generated_anim_clips") or []),
                "run_status": "active",
            },
        )
        doc = await repo.get_run(user_id=user_id, lite_run_id=lite_run_id) or doc

    if (
        doc.get("run_status") == "completed"
        and doc.get("step_phase") == "completed"
        and (not doc.get("transition_plan") or doc.get("anim_run_complete"))
    ):
        return {
            "ok": True,
            "done": True,
            "step_phase": "completed",
            "final_video_url": doc.get("final_video_url"),
            "final_assembly_error": doc.get("final_assembly_error"),
        }

    run_config = doc.get("run_config") if isinstance(doc.get("run_config"), dict) else {}
    steps_cfg = run_config.get("steps") if isinstance(run_config.get("steps"), dict) else {}
    image_policy = run_config.get("image_policy") if isinstance(run_config.get("image_policy"), dict) else {}
    video_policy = run_config.get("video_policy") if isinstance(run_config.get("video_policy"), dict) else {}
    image_model = str(image_policy.get("model") or "").strip() or None
    simple_mode = bool(image_policy.get("simple_mode"))
    i2v_model = str(video_policy.get("i2v_model") or "wan2.7-i2v").strip() or "wan2.7-i2v"
    i2v_resolution = str(video_policy.get("resolution") or "720p").strip() or "720p"
    i2v_backend = str(video_policy.get("backend") or "").strip() or None
    i2v_openrouter_model = normalize_openrouter_video_model_id(video_policy.get("openrouter_model")) or None
    prompt_mode = str(video_policy.get("prompt_mode") or "first_last_frame").strip() or "first_last_frame"
    montage_preset = str(video_policy.get("montage_preset") or "default").strip().lower() or "default"
    audio_required = bool(video_policy.get("audio_required"))
    if prompt_mode not in {"first_frame_only", "text_only", "first_last_frame"}:
        prompt_mode = "first_last_frame"
    prompt_mode, prompt_mode_policy, prompt_mode_locked = lite_effective_prompt_mode(
        prompt_mode=prompt_mode,
        montage_preset=montage_preset,
        audio_required=audio_required,
    )
    # text_only допустим для OpenRouter text-to-video моделей; совместимость проверяется в registry/model policy.
    selected_video_model = i2v_openrouter_model or i2v_model
    selected_video_prof = get_video_model_profile(selected_video_model) or {}
    if _is_first_frame_stable_model(selected_video_model):
        prompt_mode = "first_frame_only"
        prompt_mode_policy = "locked_model_first_frame_only"
        prompt_mode_locked = True
    selected_audio_mode = str(selected_video_prof.get("audio_mode") or "unknown")
    try:
        i2v_duration_sec = max(1, int(video_policy.get("duration_sec") or 4))
    except (TypeError, ValueError):
        i2v_duration_sec = 4
    try:
        scene_segment_stride = max(1, int(video_policy.get("scene_segment_stride") or 1))
    except (TypeError, ValueError):
        scene_segment_stride = 1
    try:
        reference_frame_stride = max(1, int(video_policy.get("reference_frame_stride") or 1))
    except (TypeError, ValueError):
        reference_frame_stride = 1
    require_montage_confirm = bool(video_policy.get("require_montage_confirm"))
    pipeline_variant = str(
        run_config.get("pipeline_variant") or doc.get("pipeline_variant") or "pair_i2v_between_keyframes"
    ).strip()
    phase = str(doc.get("step_phase") or "")
    await _trace("phase_enter", phase=phase, run_status=str(doc.get("run_status") or ""))

    try:
        if phase == "text_step1":
            if not openai or not getattr(openai, "configured", False):
                return await _fail_run("openai_not_configured", step="text_step1")
            raw = await lite_chat_text(
                openai,
                system=(
                    str(steps_cfg.get("text_step1_system_prompt") or "").strip()
                    or lite_environments_system_prompt(simple_mode=simple_mode)
                ),
                user=lite_environments_user_message(str(doc.get("dream_text") or "")),
            )
            env_cards, char_cards = split_lite_step1_world(raw)
            await _trace(
                "llm_step1_done",
                model="openai_chat",
                env_count=len(env_cards),
                char_count=len(char_cards),
            )
            await _update_run(
                user_id=user_id,
                lite_run_id=lite_run_id,
                patch={
                    "step1_raw": raw,
                    "env_cards": env_cards,
                    "char_cards": char_cards,
                    "step_phase": "text_step2",
                    "last_error": None,
                },
            )
            return {"ok": True, "step": "text_step1", "next_phase": "text_step2"}

        if phase == "text_step2":
            if not doc.get("step1_raw"):
                return await _fail_run("missing_step1", step="text_step2")
            if not openai or not getattr(openai, "configured", False):
                return await _fail_run("openai_not_configured", step="text_step2")
            raw, prev_raw, frame_cards = await lite_run_step2_frames_with_prev_link(
                openai,
                dream_text=str(doc.get("dream_text") or ""),
                step1_markdown=str(doc.get("step1_raw") or ""),
                step2_system_prompt=str(steps_cfg.get("text_step2_system_prompt") or "").strip() or None,
                prev_link_system_prompt=str(steps_cfg.get("text_step2_prev_link_system_prompt") or "").strip() or None,
            )
            await _update_run(
                user_id=user_id,
                lite_run_id=lite_run_id,
                patch={
                    "step2_raw": raw,
                    "step2_prev_link_raw": prev_raw,
                    "frame_cards": frame_cards,
                    "step2_runtime_entrypoint": LITE_STEP2_RUNTIME_ENTRYPOINT,
                    "step_phase": "gen_env",
                    "gen_env_i": 0,
                    "last_error": None,
                },
            )
            await _trace(
                "llm_step2_done",
                model="openai_chat",
                runtime_entrypoint=LITE_STEP2_RUNTIME_ENTRYPOINT,
                frame_count=len(frame_cards),
                keyframe_count=sum(1 for x in frame_cards if isinstance(x, dict) and bool(x.get("is_keyframe", True))),
                non_keyframe_count=sum(1 for x in frame_cards if isinstance(x, dict) and not bool(x.get("is_keyframe", True))),
                prev_link_json_len=len(str(prev_raw or "")),
            )
            return {"ok": True, "step": "text_step2", "next_phase": "gen_env"}

        if phase == "gen_env":
            env_cards = list(doc.get("env_cards") or [])
            i = int(doc.get("gen_env_i") or 0)
            if i >= len(env_cards):
                await _update_run(
                    user_id=user_id,
                    lite_run_id=lite_run_id,
                    patch={"step_phase": "gen_char", "gen_char_i": 0},
                )
                return {"ok": True, "advanced": "gen_char", "reason": "env_done"}
            c = env_cards[i]
            title = str(c.get("title") or "").strip() or f"env_{i + 1}"
            body = str(c.get("body") or "").strip()
            gen_env = dict(doc.get("generated_env") or {})
            if not body:
                gen_env[title] = {"ok": False, "urls": [], "error": "Пустое описание окружения"}
                new_i = i + 1
                patch: dict[str, Any] = {
                    "generated_env": gen_env,
                    "gen_env_i": new_i,
                    "last_error": None,
                }
                if new_i >= len(env_cards):
                    patch["step_phase"] = "gen_char"
                    patch["gen_char_i"] = 0
                await _update_run(patch=patch)
                return {"ok": True, "step": "gen_env", "index": i, "skipped": True}

            payload = await asyncio.to_thread(
                _sync_gen_env_image,
                title,
                body,
                model=image_model,
                simple_mode=simple_mode,
            )
            ok = bool(payload.get("ok"))
            urls = list(payload.get("image_urls") or [])
            err = None if ok else str(payload.get("error") or "Ошибка генерации")
            urls_safe = lite_materialize_url_list_for_mongo(
                urls,
                lite_run_id=lite_run_id,
                basename_prefix=f"env_{i}_{title}",
                user_id=int(user_id),
            )
            gen_env[title] = {"ok": ok, "urls": urls_safe, "error": err}
            new_i = i + 1
            patch = {"generated_env": gen_env, "gen_env_i": new_i, "last_error": None}
            if new_i >= len(env_cards):
                patch["step_phase"] = "gen_char"
                patch["gen_char_i"] = 0
            await _update_run(patch=patch)
            await _trace(
                "image_env_generated",
                title=title,
                ok=ok,
                model=_s(payload.get("model") or payload.get("provider_model") or "openrouter_image"),
                provider=_s(payload.get("provider") or payload.get("backend") or "openrouter"),
                fallback=_s(payload.get("fallback") or payload.get("fallback_reason") or ""),
                error=_s(err),
            )
            return {"ok": True, "step": "gen_env", "index": i, "title": title, "image_ok": ok}

        if phase == "gen_char":
            char_cards = list(doc.get("char_cards") or [])
            env_cards_for_char = list(doc.get("env_cards") or [])
            env_context_parts: list[str] = []
            for ec in env_cards_for_char[:3]:
                if not isinstance(ec, dict):
                    continue
                et = str(ec.get("title") or "").strip()
                eb = str(ec.get("body") or "").strip()
                if et or eb:
                    env_context_parts.append(f"{et}: {eb}".strip(": "))
            env_context = " | ".join(env_context_parts)[:1200]
            i = int(doc.get("gen_char_i") or 0)
            dreamer_candidates = [
                idx
                for idx, cc in enumerate(char_cards)
                if _is_dreamer_text(f"{cc.get('title') or ''} {cc.get('body') or ''}")
            ]
            dreamer_idx = dreamer_candidates[0] if dreamer_candidates else (0 if char_cards else -1)
            if i >= len(char_cards):
                await _update_run(
                    user_id=user_id,
                    lite_run_id=lite_run_id,
                    patch={"step_phase": "gen_frame", "gen_frame_i": 0},
                )
                return {"ok": True, "advanced": "gen_frame", "reason": "char_done"}
            c = char_cards[i]
            title = str(c.get("title") or "").strip() or f"char_{i + 1}"
            body = str(c.get("body") or "").strip()
            gen_char = dict(doc.get("generated_char") or {})
            if bool(simple_mode) and i != dreamer_idx:
                gen_char[title] = {
                    "ok": False,
                    "urls": [],
                    "error": "",
                    "generation_status": "skipped_simple_mode_non_dreamer",
                    "skip_reason": "simple_mode_dreamer_only_policy",
                    "skip_debug": {
                        "dreamer_idx": int(dreamer_idx),
                        "title_match": bool(_is_dreamer_title(title)),
                        "card_match": bool(_is_dreamer_text(f"{title} {body}")),
                    },
                }
                new_i = i + 1
                patch = {"generated_char": gen_char, "gen_char_i": new_i, "last_error": None}
                if new_i >= len(char_cards):
                    patch["step_phase"] = "gen_frame"
                    patch["gen_frame_i"] = 0
                await _update_run(patch=patch)
                await _trace(
                    "image_char_skipped_non_dreamer",
                    title=title,
                    simple_mode=True,
                    reason="simple_mode_dreamer_only_policy",
                    dreamer_idx=int(dreamer_idx),
                    title_match=bool(_is_dreamer_title(title)),
                    card_match=bool(_is_dreamer_text(f"{title} {body}")),
                )
                return {"ok": True, "step": "gen_char", "index": i, "title": title, "skipped": True}
            if not body:
                gen_char[title] = {"ok": False, "urls": [], "error": "Пустое описание персонажа"}
                new_i = i + 1
                patch = {"generated_char": gen_char, "gen_char_i": new_i, "last_error": None}
                if new_i >= len(char_cards):
                    patch["step_phase"] = "gen_frame"
                    patch["gen_frame_i"] = 0
                await _update_run(patch=patch)
                return {"ok": True, "step": "gen_char", "index": i, "skipped": True}

            payload = await asyncio.to_thread(
                _sync_gen_char_image,
                title,
                body,
                env_context=env_context,
                model=image_model,
            )
            ok = bool(payload.get("ok"))
            urls = list(payload.get("image_urls") or [])
            if urls:
                urls = urls[:1]
            err = None if ok else str(payload.get("error") or "Ошибка генерации")
            urls_safe = lite_materialize_url_list_for_mongo(
                urls,
                lite_run_id=lite_run_id,
                basename_prefix=f"char_{i}_{title}",
                user_id=int(user_id),
            )
            gen_char[title] = {"ok": ok, "urls": urls_safe, "error": err}
            new_i = i + 1
            patch = {"generated_char": gen_char, "gen_char_i": new_i, "last_error": None}
            if new_i >= len(char_cards):
                patch["step_phase"] = "gen_frame"
                patch["gen_frame_i"] = 0
            await _update_run(patch=patch)
            await _trace(
                "image_char_generated",
                title=title,
                ok=ok,
                model=_s(payload.get("model") or payload.get("provider_model") or "openrouter_image"),
                provider=_s(payload.get("provider") or payload.get("backend") or "openrouter"),
                fallback=_s(payload.get("fallback") or payload.get("fallback_reason") or ""),
                error=_s(err),
            )
            return {"ok": True, "step": "gen_char", "index": i, "title": title, "image_ok": ok}

        if phase == "gen_frame":
            frame_cards = list(doc.get("frame_cards") or [])
            fi = int(doc.get("gen_frame_i") or 0)
            if fi >= len(frame_cards):
                await _update_run(
                    user_id=user_id,
                    lite_run_id=lite_run_id,
                    patch={"step_phase": "transition_plan", "last_error": None},
                )
                return {"ok": True, "advanced": "transition_plan", "reason": "frames_done"}

            env_cards = list(doc.get("env_cards") or [])
            char_cards = list(doc.get("char_cards") or [])
            env_order = [str(x.get("title") or "") for x in env_cards]
            char_order = [str(x.get("title") or "") for x in char_cards]
            url_by_env = _resolved_urls_from_slots(doc.get("generated_env"))
            url_by_char = _resolved_urls_from_slots(doc.get("generated_char"))

            card = frame_cards[fi]
            title = str(card.get("title") or f"Кадр {fi + 1}")
            opora = str(card.get("opora") or "")
            izm = str(card.get("izmenenie") or "")
            kad = str(card.get("kad") or "").strip()
            is_keyframe = bool(card.get("is_keyframe", True))
            keyframe_reason = str(card.get("keyframe_reason") or "").strip()
            prev_title = (
                str(frame_cards[fi - 1].get("title") or f"кадр {fi}") if fi > 0 else None
            )
            last_url = doc.get("last_success_frame_url")
            if isinstance(last_url, str):
                last_url = last_url.strip() or None
            else:
                last_url = None
            if last_url:
                last_url = lite_resolve_image_url_for_external_api(last_url) or last_url

            prior_entries = list(doc.get("generated_frames") or [])
            up_eff, forced_break = lite_resolve_use_previous_frame(
                card,
                fi,
                prior_frame_entries=prior_entries,
                simple_mode=bool(simple_mode),
            )
            ref_urls, ref_note, ref_bundle, ref_slots = collect_lite_frame_reference_urls(
                fi,
                card,
                url_by_env,
                env_order,
                url_by_char,
                char_order,
                last_url if up_eff else None,
                use_previous_for_refs=up_eff,
                prev_frame_title=prev_title,
                simple_mode=simple_mode,
            )
            ref_urls_for_api = _resolve_ref_urls_for_external_api(ref_urls)
            env_label_from_slots, dreamer_label_from_slots = _simple_labels_from_ref_slots(ref_slots)
            br = str(card.get("base_reference") or "").strip()
            env_line = "—"
            if br:
                _, env_line = resolve_lite_env_url(br, url_by_env, env_order)
            chars_line = ", ".join(str(x) for x in (card.get("character_references") or [])) or "—"
            img_prompt = build_lite_frame_image_prompt(
                kad,
                izm,
                use_previous_for_refs=up_eff,
                simple_mode=simple_mode,
                environment_label=env_label_from_slots or (env_line if simple_mode else ""),
                dreamer_label=dreamer_label_from_slots or (chars_line if simple_mode else ""),
            )
            canonical_slots = lite_ref_slots_canonical_for_ui(
                fi,
                up_eff,
                forced_break,
                ref_slots,
                ref_bundle,
            )
            refs_summary_line = lite_refs_summary_for_ui(canonical_slots)

            if bool(simple_mode) and not is_keyframe:
                frames_list = list(doc.get("generated_frames") or [])
                entry: dict[str, Any] = {
                    "index": fi,
                    "title": title,
                    "opora": opora,
                    "izmenenie": izm,
                    "kad": kad,
                    "refs_summary_line": refs_summary_line,
                    "base_reference": str(card.get("base_reference") or ""),
                    "character_references": list(card.get("character_references") or []),
                    "use_previous_frame": card.get("use_previous_frame"),
                    "use_previous_frame_resolved": up_eff,
                    "forced_prev_chain_break": forced_break,
                    "prev_resolution_reason": str(card.get("prev_resolution_reason") or ""),
                    "prev_pair_state": str(card.get("prev_pair_state") or ""),
                    "is_keyframe": False,
                    "keyframe_reason": keyframe_reason,
                    "simple_mode": simple_mode,
                    "ref_bundle": ref_bundle,
                    "ref_slots": _compact_ref_slots_for_mongo(canonical_slots),
                    "img_prompt": "",
                    "reference_image_urls": [],
                    "reference_image_urls_ui": [],
                    "requested_model": str(image_model or "").strip(),
                    "effective_model": str(image_model or "").strip(),
                    "openrouter_models_tried": [],
                    "ok": False,
                    "urls": [],
                    "error": "",
                    "ref_note": ref_note,
                    "generation_status": "skipped_non_keyframe",
                    "image_generated_ok": False,
                    "usage_unavailable": True,
                }
                frames_list.append(entry)
                new_fi = fi + 1
                patch: dict[str, Any] = {
                    "generated_frames": frames_list,
                    "gen_frame_i": new_fi,
                    "last_error": None,
                }
                if new_fi >= len(frame_cards):
                    patch["step_phase"] = "transition_plan"
                await _update_run(patch=patch)
                await _trace(
                    "image_frame_skipped_non_keyframe",
                    frame_index=fi,
                    title=title,
                    reason=keyframe_reason or "non_keyframe_by_classifier",
                    simple_mode=bool(simple_mode),
                )
                return {
                    "ok": True,
                    "step": "gen_frame",
                    "index": fi,
                    "title": title,
                    "image_ok": False,
                    "skipped_non_keyframe": True,
                }
            logger.info(
                (
                    "dream_lite frame_request user_id=%s run=%s fi=%s simple_mode=%s "
                    "ref_bundle=%s reference_roles=%s reference_image_urls_count=%s reference_image_urls_short=%s "
                    "prev_reason=%s prev_pair_state=%s ref_text_risk=%s"
                ),
                int(user_id),
                str(lite_run_id),
                int(fi),
                bool(simple_mode),
                str(ref_bundle),
                [str(s.get("role") or "") for s in list(ref_slots or [])],
                len(ref_urls_for_api),
                _short_ref_urls(ref_urls_for_api),
                str(card.get("prev_resolution_reason") or ""),
                str(card.get("prev_pair_state") or ""),
                _ref_text_risk_slots(ref_slots),
            )

            request_ts = time.time()
            payload = await asyncio.to_thread(_sync_gen_frame_image, img_prompt, ref_urls_for_api, model=image_model)
            first_response_ts = time.time()
            completed_ts = time.time()
            ok = bool(payload.get("ok"))
            urls = list(payload.get("image_urls") or [])
            err = None if ok else str(payload.get("error") or "Ошибка генерации")
            requested_model = str(image_model or "").strip()
            effective_model = _s(payload.get("model") or payload.get("provider_model") or image_model)
            models_tried = [str(x).strip() for x in list(payload.get("models_tried") or []) if str(x).strip()]
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            tokens_in = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            tokens_out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or (tokens_in + tokens_out) or 0)
            ref_stored = lite_materialize_url_list_for_mongo(
                list(ref_urls_for_api),
                lite_run_id=lite_run_id,
                basename_prefix=f"ref_frame_{fi}",
                user_id=int(user_id),
            )
            urls_stored = lite_materialize_url_list_for_mongo(
                urls,
                lite_run_id=lite_run_id,
                basename_prefix=f"out_frame_{fi}",
                user_id=int(user_id),
            )

            frames_list = list(doc.get("generated_frames") or [])
            entry: dict[str, Any] = {
                "index": fi,
                "title": title,
                "opora": opora,
                "izmenenie": izm,
                "kad": kad,
                "refs_summary_line": refs_summary_line,
                "base_reference": str(card.get("base_reference") or ""),
                "character_references": list(card.get("character_references") or []),
                "use_previous_frame": card.get("use_previous_frame"),
                "use_previous_frame_resolved": up_eff,
                "forced_prev_chain_break": forced_break,
                "prev_resolution_reason": str(card.get("prev_resolution_reason") or ""),
                "prev_pair_state": str(card.get("prev_pair_state") or ""),
                "is_keyframe": is_keyframe,
                "keyframe_reason": keyframe_reason,
                "simple_mode": simple_mode,
                "ref_bundle": ref_bundle,
                "ref_slots": _compact_ref_slots_for_mongo(canonical_slots),
                "img_prompt": img_prompt,
                "reference_image_urls": ref_stored,
                "reference_image_urls_ui": lite_ref_urls_for_ui(ref_stored),
                "refs_sent_count": len(ref_urls_for_api),
                "refs_sent_roles": [str(s.get("role") or "") for s in list(ref_slots or []) if s.get("in_api", True) is not False],
                "refs_policy_result": ("simple_dreamer_env_only" if bool(simple_mode) else "standard_frame_refs"),
                "requested_model": requested_model,
                "selected_model": requested_model,
                "effective_model": effective_model,
                "openrouter_models_tried": models_tried,
                "ok": ok,
                "urls": urls_stored,
                "error": err,
                "ref_note": ref_note,
                "generation_status": ("generated" if ok else "error"),
                "image_generated_ok": bool(ok and urls_stored),
                "request_at": request_ts,
                "first_response_at": first_response_ts,
                "completed_at": completed_ts,
                "duration_ms": int((completed_ts - request_ts) * 1000),
                "provider_latency_ms": int((first_response_ts - request_ts) * 1000),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "total_tokens": total_tokens,
                "usage_unavailable": not bool(usage),
            }
            frames_list.append(entry)

            new_fi = fi + 1
            patch: dict[str, Any] = {
                "generated_frames": frames_list,
                "gen_frame_i": new_fi,
                "last_error": None,
            }
            if ok and urls_stored:
                patch["last_success_frame_url"] = urls_stored[0]
            if new_fi >= len(frame_cards):
                patch["step_phase"] = "transition_plan"
            await _update_run(patch=patch)
            await _trace(
                "image_frame_generated",
                frame_index=fi,
                title=title,
                ok=ok,
                model=effective_model,
                requested_model=requested_model,
                models_tried=models_tried,
                selected_model=requested_model,
                refs_sent_count=len(ref_urls_for_api),
                refs_sent_roles=[str(s.get("role") or "") for s in list(ref_slots or []) if s.get("in_api", True) is not False],
                refs_policy_result=("simple_dreamer_env_only" if bool(simple_mode) else "standard_frame_refs"),
                provider=_s(payload.get("provider") or payload.get("backend") or "openrouter"),
                fallback=_s(payload.get("fallback") or payload.get("fallback_reason") or ""),
                error=_s(err),
                duration_ms=int((completed_ts - request_ts) * 1000),
                provider_latency_ms=int((first_response_ts - request_ts) * 1000),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                total_tokens=total_tokens,
            )
            record_metric(
                {
                    "stage": "gen_frame",
                    "user_id": int(user_id),
                    "lite_run_id": str(lite_run_id),
                    "model_id": effective_model,
                    "requested_model": requested_model,
                    "effective_model": effective_model,
                    "request_at": request_ts,
                    "first_response_at": first_response_ts,
                    "completed_at": completed_ts,
                    "duration_ms": int((completed_ts - request_ts) * 1000),
                    "provider_latency_ms": int((first_response_ts - request_ts) * 1000),
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "total_tokens": total_tokens,
                    "usage_unavailable": total_tokens <= 0,
                }
            )
            return {
                "ok": True,
                "step": "gen_frame",
                "index": fi,
                "title": title,
                "image_ok": ok,
            }

        if phase == "transition_plan":
            if not openai or not getattr(openai, "configured", False):
                return await _fail_run("openai_not_configured", step="transition_plan")
            frames = list(doc.get("generated_frames") or [])
            env_cards = list(doc.get("env_cards") or [])
            char_cards = list(doc.get("char_cards") or [])
            n = len(frames)
            if n <= 1:
                plan = lite_default_transition_plan(n)
                await _update_run(
                    user_id=user_id,
                    lite_run_id=lite_run_id,
                    patch={
                        "transition_plan": plan,
                        "transition_plan_raw": None,
                        "step_phase": "anim_i2v",
                        "gen_anim_i": 0,
                        "anim_run_complete": False,
                        "last_error": None,
                    },
                )
                return {"ok": True, "step": "transition_plan", "skipped": True, "next_phase": "anim_i2v"}

            montage_preset = lite_resolve_montage_preset(
                selected_video_model=selected_video_model,
                configured_preset=str(video_policy.get("montage_preset") or ""),
            )
            user = lite_transitions_user_message(
                dream_text=str(doc.get("dream_text") or ""),
                env_cards=env_cards,
                char_cards=char_cards,
                generated_frames=frames,
                montage_preset=montage_preset,
            )
            if montage_preset == "seedance":
                base_transition_prompt = str(steps_cfg.get("transition_plan_seedance_system_prompt") or "").strip()
                if not base_transition_prompt:
                    base_transition_prompt = lite_transitions_seedance_system_prompt()
            elif montage_preset == "wan_2_6_single_anchor":
                base_transition_prompt = str(steps_cfg.get("transition_plan_wan26_system_prompt") or "").strip()
                if not base_transition_prompt:
                    base_transition_prompt = lite_transitions_wan26_system_prompt()
            elif montage_preset == "kling_v3_reference_motion":
                base_transition_prompt = str(
                    steps_cfg.get("transition_plan_kling_reference_system_prompt") or ""
                ).strip()
                if not base_transition_prompt:
                    base_transition_prompt = lite_transitions_kling_reference_system_prompt()
            else:
                base_transition_prompt = str(steps_cfg.get("transition_plan_system_prompt") or "").strip()
                if not base_transition_prompt:
                    base_transition_prompt = lite_transitions_system_prompt()
            raw = await lite_chat_text(
                openai,
                system=lite_build_transition_system_prompt(
                    base_prompt=base_transition_prompt,
                    prompt_mode=prompt_mode,
                    audio_required=audio_required,
                    montage_preset=montage_preset,
                ),
                user=user,
            )
            plan = parse_lite_transition_plan_from_model_text(raw, n)
            plan = lite_transition_plan_with_selection(
                plan,
                n,
                generated_frames=frames,
            )

            next_after_plan = "montage_confirm" if (require_montage_confirm and n > 1) else "anim_i2v"
            await _update_run(
                user_id=user_id,
                lite_run_id=lite_run_id,
                patch={
                    "transition_plan": plan,
                    "transition_plan_raw": raw,
                    "step_phase": next_after_plan,
                    "gen_anim_i": 0,
                    "anim_run_complete": False,
                    "last_error": None,
                },
            )
            await _trace(
                "transition_plan_done",
                model="openai_chat",
                prompt_mode=prompt_mode,
                montage_preset=montage_preset,
                audio_required=audio_required,
                audio_mode=selected_audio_mode,
                transitions=len(list(plan.get("transitions") or [])),
                scenes=len(list(plan.get("scenes") or [])),
                next_phase=next_after_plan,
            )
            out_tp: dict[str, Any] = {
                "ok": True,
                "step": "transition_plan",
                "next_phase": next_after_plan,
                "step_phase": next_after_plan,
            }
            if next_after_plan == "montage_confirm":
                out_tp["await_montage_confirm"] = True
                out_tp["lite_run_id"] = lite_run_id
            return out_tp

        if phase == "montage_confirm":
            return {
                "ok": True,
                "step": "montage_confirm",
                "await_montage_confirm": True,
                "step_phase": "montage_confirm",
                "lite_run_id": lite_run_id,
                "next_phase": "montage_confirm",
            }

        if phase == "anim_i2v":
            plan = doc.get("transition_plan") or {}
            frames = list(doc.get("generated_frames") or [])
            segments = lite_collect_animate_i2v_segments(
                plan,
                frames,
                prompt_mode=prompt_mode,
                montage_preset=montage_preset,
                audio_required=audio_required,
                scene_segment_stride=scene_segment_stride,
                reference_frame_stride=reference_frame_stride,
            )
            ai = int(doc.get("gen_anim_i") or 0)
            owner_key = f"lite_{int(user_id)}"

            if ai >= len(segments):
                await _update_run(
                    user_id=user_id,
                    lite_run_id=lite_run_id,
                    patch={
                        "step_phase": "finalize_clips",
                        "anim_run_complete": True,
                        "last_error": None,
                    },
                )
                return {
                    "ok": True,
                    "step": "anim_i2v",
                    "skipped": True,
                    "next_phase": "finalize_clips",
                    "animate_segments": len(segments),
                }

            seg = segments[ai]
            seg_runtime = dict(seg)
            if str(seg.get("segment_mode") or "").strip().lower() == "single_anchor":
                seg_runtime["last_frame_url"] = ""
            if prompt_mode in {"first_frame_only", "text_only"}:
                seg_runtime["last_frame_url"] = ""
            if prompt_mode == "text_only":
                seg_runtime["motion_prompt"] = f"{_s(seg.get('motion_prompt'))}\n\nMode: text_only (last_frame disabled)."
            try:
                seg_duration_sec = int(seg.get("duration_sec") or 0)
            except (TypeError, ValueError):
                seg_duration_sec = 0
            if seg_duration_sec <= 0:
                seg_duration_sec = i2v_duration_sec
            calculated_duration_sec = seg_duration_sec
            limits = selected_video_prof.get("limits") if isinstance(selected_video_prof, dict) else {}
            supported_durations = []
            if isinstance(limits, dict):
                raw_durations = list(limits.get("supported_durations") or [])
                for raw_d in raw_durations:
                    try:
                        d = int(raw_d)
                    except (TypeError, ValueError):
                        continue
                    if d > 0:
                        supported_durations.append(d)
            seg_duration_sec = _normalize_provider_duration_sec(
                seg_duration_sec,
                backend=i2v_backend,
                openrouter_model=i2v_openrouter_model,
                supported_durations=supported_durations,
            )
            payload = await asyncio.to_thread(
                _sync_lite_i2v_segment,
                seg_runtime,
                owner_key=owner_key,
                lite_run_id=lite_run_id,
                segment_index=ai,
                i2v_model=i2v_model,
                duration_sec=seg_duration_sec,
                resolution=i2v_resolution,
                video_backend=i2v_backend,
                openrouter_model=i2v_openrouter_model,
            )
            clip_entry: dict[str, Any] = {
                "segment_index": ai,
                "from_frame_index": seg["from_frame_index"],
                "to_frame_index": seg["to_frame_index"],
                "motion_prompt": seg.get("motion_prompt"),
                "final_prompt": seg.get("final_prompt"),
                "segment_story": seg.get("segment_story"),
                "voiceover_text": seg.get("voiceover_text"),
                "calculated_duration_sec": calculated_duration_sec,
                "provider_duration_sec": seg_duration_sec,
                "duration_sec": seg_duration_sec,
                "prompt_mode": prompt_mode,
                "effective_prompt_mode": str(seg.get("effective_prompt_mode") or prompt_mode),
                "effective_prompt_policy": str(seg.get("effective_prompt_policy") or prompt_mode_policy),
                "prompt_mode_locked": bool(seg.get("prompt_mode_locked", prompt_mode_locked)),
                "phase_timing_text_present": bool(seg.get("phase_timing_text_present")),
                "micro_act_contract_applied": bool(seg.get("micro_act_contract_applied")),
                "segment_mode": str(seg.get("segment_mode") or "pairwise"),
                "is_scene_start": bool(seg.get("is_scene_start")),
                "anchor_role": str(seg.get("anchor_role") or ""),
                "pre_anchor_beats": str(seg.get("pre_anchor_beats") or ""),
                "anchor_frame_state": str(seg.get("anchor_frame_state") or ""),
                "post_anchor_beats": str(seg.get("post_anchor_beats") or ""),
                "job_id": payload.get("job_id"),
                "status": payload.get("status"),
                "video_url": payload.get("video_url"),
                "ok": bool(payload.get("ok")),
                "error": payload.get("error"),
                "request_at": payload.get("request_at"),
                "first_response_at": payload.get("first_response_at"),
                "completed_at": payload.get("completed_at"),
                "duration_ms": payload.get("duration_ms"),
                "provider_latency_ms": payload.get("provider_latency_ms"),
                "requested_model": payload.get("requested_model"),
                "effective_model": payload.get("effective_model"),
                "video_backend": payload.get("video_backend"),
                "tokens_in": int(payload.get("tokens_in") or 0),
                "tokens_out": int(payload.get("tokens_out") or 0),
                "total_tokens": int(payload.get("total_tokens") or 0),
                "usage_unavailable": bool(not payload.get("total_tokens")),
            }
            clips = list(doc.get("generated_anim_clips") or [])
            clips.append(clip_entry)
            new_ai = ai + 1
            patch_a: dict[str, Any] = {
                "generated_anim_clips": clips,
                "gen_anim_i": new_ai,
                "last_error": None,
            }
            if new_ai >= len(segments):
                patch_a["step_phase"] = "finalize_clips"
                patch_a["anim_run_complete"] = True
            await _update_run(patch=patch_a)
            await _trace(
                "i2v_segment_created",
                segment_index=ai,
                from_frame=seg["from_frame_index"],
                to_frame=seg["to_frame_index"],
                job_id=_s(payload.get("job_id")),
                status=_s(payload.get("status")),
                ok=bool(payload.get("ok")),
                model=_s(payload.get("effective_model") or payload.get("requested_model") or i2v_model),
                requested_model=_s(payload.get("requested_model") or i2v_model),
                backend=_s(payload.get("video_backend") or i2v_backend or get_settings().video_generation_backend or "dashscope"),
                prompt_mode=prompt_mode,
                effective_prompt_mode=_s(seg.get("effective_prompt_mode") or prompt_mode),
                effective_prompt_policy=_s(seg.get("effective_prompt_policy") or prompt_mode_policy),
                prompt_mode_locked=bool(seg.get("prompt_mode_locked", prompt_mode_locked)),
                segment_mode=_s(seg.get("segment_mode") or "pairwise"),
                is_scene_start=bool(seg.get("is_scene_start")),
                anchor_role=_s(seg.get("anchor_role")),
                phase_timing_text_present=bool(seg.get("phase_timing_text_present")),
                micro_act_contract_applied=bool(seg.get("micro_act_contract_applied")),
                duration_sec=seg_duration_sec,
                has_voiceover=bool(str(seg.get("voiceover_text") or "").strip()),
                duration_ms=int(payload.get("duration_ms") or 0),
                provider_latency_ms=int(payload.get("provider_latency_ms") or 0),
                tokens_in=int(payload.get("tokens_in") or 0),
                tokens_out=int(payload.get("tokens_out") or 0),
                total_tokens=int(payload.get("total_tokens") or 0),
                error=_s(payload.get("error")),
            )
            record_metric(
                {
                    "stage": "anim_i2v",
                    "user_id": int(user_id),
                    "lite_run_id": str(lite_run_id),
                    "segment_index": ai,
                    "duration_sec": seg_duration_sec,
                    "has_voiceover": bool(str(seg.get("voiceover_text") or "").strip()),
                    "model_id": _s(payload.get("effective_model") or payload.get("requested_model") or i2v_model),
                    "requested_model": _s(payload.get("requested_model") or i2v_model),
                    "effective_model": _s(payload.get("effective_model") or payload.get("requested_model") or i2v_model),
                    "request_at": payload.get("request_at"),
                    "first_response_at": payload.get("first_response_at"),
                    "completed_at": payload.get("completed_at"),
                    "duration_ms": int(payload.get("duration_ms") or 0),
                    "provider_latency_ms": int(payload.get("provider_latency_ms") or 0),
                    "tokens_in": int(payload.get("tokens_in") or 0),
                    "tokens_out": int(payload.get("tokens_out") or 0),
                    "total_tokens": int(payload.get("total_tokens") or 0),
                    "usage_unavailable": bool(not payload.get("total_tokens")),
                }
            )
            return {
                "ok": True,
                "step": "anim_i2v",
                "index": ai,
                "job_id": payload.get("job_id"),
                "video_job_ok": bool(payload.get("ok")),
                "done": False,
                "next_phase": "finalize_clips" if new_ai >= len(segments) else "anim_i2v",
            }

        if phase == "finalize_clips":
            patch_f = await asyncio.to_thread(
                _sync_finalize_lite_clips,
                doc,
                user_id=user_id,
                lite_run_id=lite_run_id,
            )
            await _update_run(patch=patch_f)
            await _trace(
                "finalize_done",
                final_video_url=_s(patch_f.get("final_video_url")),
                final_assembly_error=_s(patch_f.get("final_assembly_error")),
                run_status=_s(patch_f.get("run_status")),
                failed_transitions=len(list(patch_f.get("failed_transitions") or [])),
            )
            return {
                "ok": True,
                "step": "finalize_clips",
                "done": True,
                "step_phase": "completed",
                "final_video_url": patch_f.get("final_video_url"),
                "final_assembly_error": patch_f.get("final_assembly_error"),
            }

        return await _fail_run(f"unknown_phase:{phase}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("dream_lite_run step failed")
        return await _fail_run(str(exc))


def _resolve_previous_frame_url_for_lite_frame_preview(
    doc: dict[str, Any],
    frame_index: int,
) -> tuple[str | None, str]:
    """
    URL предыдущего кадра для refs — как у воркера при генерации кадра `frame_index`,
    но после завершения run берём из generated_frames[fi-1], а не только last_success_frame_url.
    """
    fi = int(frame_index)
    if fi <= 0:
        return None, "первый кадр — предыдущего нет"
    frames = list(doc.get("generated_frames") or [])
    for ent in frames:
        if not isinstance(ent, dict):
            continue
        try:
            ix = int(ent.get("index") if ent.get("index") is not None else -1)
        except (TypeError, ValueError):
            continue
        if ix == fi - 1:
            urls = list(ent.get("urls") or [])
            if urls:
                u0 = str(urls[0]).strip()
                resolved = lite_resolve_image_url_for_external_api(u0) or u0
                return resolved, f"generated_frames[{fi - 1}] (index={fi - 1})"
    lu = doc.get("last_success_frame_url")
    if isinstance(lu, str) and lu.strip():
        u0 = lu.strip()
        resolved = lite_resolve_image_url_for_external_api(u0) or u0
        return resolved, "last_success_frame_url (fallback; предыдущий кадр в списке не найден)"
    return None, "нет URL предыдущего кадра — цепочка prev может уйти в fallback env+chars"


def build_lite_frame_image_preview_bundle(
    doc: dict[str, Any],
    frame_index: int,
    *,
    image_model_override: str | None = None,
    preview_mode: str = "resolved",
    negative_prompt: str | None = None,
    seed: str | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    extra_reference_urls: list[str] | None = None,
) -> dict[str, Any]:
    """
    Тот же контракт, что `phase == gen_frame` в process_dream_lite_run_step:
    промпт кадра, ref_urls для OpenRouter, параметры 9:16 / 1K, модель из run_config (или override).
    Без сетевых вызовов.
    """
    frame_cards = list(doc.get("frame_cards") or [])
    fi = int(frame_index)
    if fi < 0 or fi >= len(frame_cards):
        return {
            "ok": False,
            "error": f"frame_index вне диапазона 0..{max(0, len(frame_cards) - 1)}",
            "frame_count": len(frame_cards),
        }

    run_config = doc.get("run_config") if isinstance(doc.get("run_config"), dict) else {}
    image_policy = run_config.get("image_policy") if isinstance(run_config.get("image_policy"), dict) else {}
    cfg_model = str(image_policy.get("model") or "").strip() or None
    image_model = (image_model_override or "").strip() or cfg_model
    simple_mode = bool(image_policy.get("simple_mode"))

    env_cards = list(doc.get("env_cards") or [])
    char_cards = list(doc.get("char_cards") or [])
    env_order = [str(x.get("title") or "") for x in env_cards]
    char_order = [str(x.get("title") or "") for x in char_cards]
    url_by_env = _resolved_urls_from_slots(doc.get("generated_env"))
    url_by_char = _resolved_urls_from_slots(doc.get("generated_char"))

    card = frame_cards[fi]
    title = str(card.get("title") or f"Кадр {fi + 1}")
    izm = str(card.get("izmenenie") or "")
    kad = str(card.get("kad") or "").strip()
    prev_title = str(frame_cards[fi - 1].get("title") or f"кадр {fi}") if fi > 0 else None

    planned_mode = str(preview_mode or "").strip().lower() == "planned"
    last_url, prev_url_source = _resolve_previous_frame_url_for_lite_frame_preview(doc, fi)
    is_keyframe = bool(card.get("is_keyframe", True))
    keyframe_reason = str(card.get("keyframe_reason") or "").strip()

    prior_entries = list(doc.get("generated_frames") or [])
    up_eff, forced_break = lite_resolve_use_previous_frame(
        card,
        fi,
        prior_frame_entries=prior_entries,
        simple_mode=bool(simple_mode),
    )
    ref_urls, ref_note, ref_bundle, ref_slots = collect_lite_frame_reference_urls(
        fi,
        card,
        url_by_env,
        env_order,
        url_by_char,
        char_order,
        last_url if up_eff else None,
        use_previous_for_refs=up_eff,
        prev_frame_title=prev_title,
        preview_mode=planned_mode,
        simple_mode=simple_mode,
    )
    ref_urls_for_api = _resolve_ref_urls_for_external_api(ref_urls)
    extra_refs = [str(x).strip() for x in (extra_reference_urls or []) if str(x).strip()]
    if extra_refs:
        ref_urls_for_api = list(dict.fromkeys([*ref_urls_for_api, *_resolve_ref_urls_for_external_api(extra_refs)]))[:8]
    env_label_from_slots, dreamer_label_from_slots = _simple_labels_from_ref_slots(ref_slots)
    br = str(card.get("base_reference") or "").strip()
    env_line = "—"
    if br:
        _, env_line = resolve_lite_env_url(br, url_by_env, env_order)
    chars_line = ", ".join(str(x) for x in (card.get("character_references") or [])) or "—"
    canonical_slots = lite_ref_slots_canonical_for_ui(
        fi,
        up_eff,
        forced_break,
        ref_slots,
        ref_bundle,
    )
    refs_summary_line = lite_refs_summary_for_ui(canonical_slots)
    img_prompt = build_lite_frame_image_prompt(
        kad,
        izm,
        use_previous_for_refs=up_eff,
        simple_mode=simple_mode,
        environment_label=env_label_from_slots or (env_line if simple_mode else ""),
        dreamer_label=dreamer_label_from_slots or (chars_line if simple_mode else ""),
    )

    ratio = (aspect_ratio or "").strip() or LITE_OPENROUTER_IMAGE_ASPECT_RATIO
    res = (resolution or "").strip() or LITE_OPENROUTER_IMAGE_SIZE
    tool_kwargs: dict[str, Any] = {
        "prompt": img_prompt.strip(),
        "reference_image_urls": ref_urls_for_api if ref_urls_for_api else None,
        "aspect_ratio": ratio,
        "image_size": res,
        "model": image_model,
        "strict_model": bool((image_model or "").strip()),
    }
    if (negative_prompt or "").strip():
        tool_kwargs["negative_prompt"] = (negative_prompt or "").strip()
    if (seed or "").strip():
        tool_kwargs["seed"] = (seed or "").strip()

    policy = run_config.get("reference_policy") if isinstance(run_config.get("reference_policy"), dict) else {}
    fallback_policy = run_config.get("fallback_policy") if isinstance(run_config.get("fallback_policy"), dict) else {}
    char_ref_ids = [str(x).strip() for x in (card.get("character_references") or []) if str(x).strip()]
    planned_slots: list[dict[str, Any]] = []
    if str(card.get("base_reference") or "").strip():
        br = str(card.get("base_reference") or "").strip()
        planned_slots.append(
            {
                "role": "environment_reference",
                "id": br,
                "required": True,
                "resolved": bool(url_by_env.get(br)),
                "url": url_by_env.get(br),
            }
        )
    for cid in char_ref_ids:
        planned_slots.append(
            {
                "role": "character_reference",
                "id": cid,
                "required": True,
                "resolved": bool(url_by_char.get(cid)),
                "url": url_by_char.get(cid),
            }
        )
    if fi > 0 and up_eff:
        planned_slots.append(
            {
                "role": "previous_frame",
                "id": str(fi - 1),
                "required": True,
                "resolved": bool(last_url),
                "url": last_url,
            }
        )

    missing_refs = [f"{x.get('role')}:{x.get('id')}" for x in planned_slots if bool(x.get("required")) and not bool(x.get("resolved"))]

    internal_payload: dict[str, Any] = {
        "task_type": "text_to_image",
        "frame_index": fi,
        "prompt": img_prompt.strip(),
        "negative_prompt": (negative_prompt or "").strip(),
        "seed": (seed or "").strip(),
        "reference_images": list(ref_urls_for_api),
        "aspect_ratio": ratio,
        "resolution": res,
        "character_references": char_ref_ids,
        "environment_references": [str(card.get("base_reference") or "").strip()] if str(card.get("base_reference") or "").strip() else [],
        "previous_frame_reference": (last_url if up_eff else None),
        "style_references": [],
        "required_reference_slots": [x for x in planned_slots if bool(x.get("required"))],
        "optional_reference_slots": [x for x in planned_slots if not bool(x.get("required"))],
        "missing_required_references": missing_refs,
        "reference_selection_reason": {
            "ref_bundle": ref_bundle,
            "ref_note": ref_note,
            "refs_summary_line": refs_summary_line,
            "refs_sent_count": len(ref_urls_for_api),
        },
        "policies": {
            "use_previous_frame": up_eff,
            "prev_continuity_policy": ("simple_mode_cap2_pair_only" if simple_mode else "scene_aware_no_hard_limit"),
            "reference_priority": policy.get("reference_priority", ["previous_frame", "environment", "character"]),
            "fallback_rules": fallback_policy,
        },
        "step_id": f"gen_frame:{fi}",
        "scene_id": str(doc.get("lite_run_id") or doc.get("_id") or ""),
    }

    return {
        "ok": True,
        "frame_index": fi,
        "frame_title": title,
        "card": {
            "opora": str(card.get("opora") or ""),
            "izmenenie": izm,
            "kad": kad,
            "base_reference": str(card.get("base_reference") or ""),
            "character_references": list(card.get("character_references") or []),
            "use_previous_frame": card.get("use_previous_frame"),
            "is_keyframe": is_keyframe,
            "keyframe_reason": keyframe_reason,
        },
        "image_model_from_run_config": cfg_model,
        "image_model_resolved": image_model,
        "previous_frame_url_source": prev_url_source,
        "use_previous_frame_resolved": up_eff,
        "forced_prev_chain_break": forced_break,
        "is_keyframe": is_keyframe,
        "keyframe_reason": keyframe_reason,
        "prev_resolution_reason": str(card.get("prev_resolution_reason") or ""),
        "prev_pair_state": str(card.get("prev_pair_state") or ""),
        "simple_mode": simple_mode,
        "refs_summary_line": refs_summary_line,
        "ref_note": ref_note,
        "ref_bundle": ref_bundle,
        "ref_slots": canonical_slots,
        "img_prompt": img_prompt,
        "reference_image_urls": ref_urls,
        "reference_image_urls_external": ref_urls_for_api,
        "missing_required_references": missing_refs,
        "planned_reference_slots": planned_slots,
        "preview_mode": "planned" if planned_mode else "resolved",
        "tool_generate_image_openrouter_kwargs": tool_kwargs,
        "internal_payload": internal_payload,
    }
