"""Локальная dev-консоль: FastAPI + Jinja2 + HTMX (только 127.0.0.1)."""
from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import html
import json
import re
import time
import uuid
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from pymongo import MongoClient
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from core.config.settings import Settings, get_settings
from core.observability.repository import ObservabilityRepository
from services.assets.asset_source_service import (
    AssetSourceError,
    dream_asset_to_data_uri,
    load_local_file_as_data_uri,
    resolve_dream_asset_image_ref_for_qwen,
)
from services.observability.dev_messages import get_message_detail, get_recent_messages
from services.observability.dev_usage_recorder import (
    normalize_openrouter_usage,
    record_dev_usage,
)
from services.observability.tools_dev import (
    build_tools_frame_context,
    get_execution_detail,
    load_policies_extra,
    load_tool_overrides,
    save_policies_extra,
    save_tool_overrides,
    trace_timeline,
)
from services.dreams.dream_lite_service import (
    default_run_config,
    stage_contract_catalog,
    video_policy_bundle_for_montage_preset,
)
from services.dreams.model_capability_registry import (
    build_provider_request_from_internal_payload,
    get_model_profile,
    model_capability_registry,
)
from services.dreams.video_model_capability_registry import (
    build_provider_request_from_internal_video_payload,
    get_video_model_profile,
    openrouter_video_models_catalog,
    video_model_mode_compatible,
    video_model_capability_registry,
    video_model_supported_prompt_modes,
)
from services.llm.system_prompt_loader import (
    merge_with_global_model_policy,
    read_dream_director_keyframes_raw,
    read_dream_director_references_raw,
    read_dream_image_prompts_raw,
    read_dream_intent_routing_raw,
    read_dream_pipeline_lite_environments_raw,
    read_dream_pipeline_lite_environments_simple_raw,
    read_dream_pipeline_lite_frames_raw,
    read_dream_pipeline_lite_frames_prev_link_raw,
    read_dream_pipeline_lite_transitions_kling_ref_raw,
    read_dream_pipeline_lite_transitions_raw,
    read_dream_pipeline_lite_transitions_seedance_raw,
    read_dream_pipeline_lite_transitions_wan26_raw,
    read_global_model_policy_raw,
    read_system_prompt_raw,
    SystemPromptError,
    write_dream_beat_planner_raw,
    write_dream_decomposition_raw,
    write_dream_director_keyframes_raw,
    write_dream_director_keyframes_user_contract_raw,
    write_dream_director_references_raw,
    write_dream_director_references_user_contract_raw,
    write_dream_image_prompts_raw,
    write_dream_pipeline_lite_environments_raw,
    write_dream_pipeline_lite_environments_simple_raw,
    write_dream_pipeline_lite_frames_raw,
    write_dream_pipeline_lite_frames_prev_link_raw,
    write_dream_pipeline_lite_transitions_kling_ref_raw,
    write_dream_pipeline_lite_transitions_raw,
    write_dream_pipeline_lite_transitions_seedance_raw,
    write_dream_pipeline_lite_transitions_wan26_raw,
    write_dream_scene_motion_decompose_raw,
    write_dream_intent_routing_raw,
    write_global_model_policy_raw,
    write_system_prompt_raw,
)
from services.observability.dream_director_playground import (
    build_assembler_final_scenes_shim,
    default_keyframes_system_prompt,
    default_references_system_prompt,
    keyframes_contract_user_block,
    normalize_global_references_block,
    normalize_key_frames_bundle,
    parse_asset_context_playground,
    PLAYGROUND_POLICY,
    director_dream_text_user_block,
    references_contract_user_block,
)
from services.observability.dream_lite_run_worker import (
    build_lite_frame_image_preview_bundle,
    process_dream_lite_run_step,
)
from services.images.openrouter_image_models_catalog import catalog_models_for_template
from services.observability.dream_pipeline_lite import (
    LITE_PLAYGROUND_USER_ID,
    LITE_STEP2_RUNTIME_ENTRYPOINT,
    lite_chat_text,
    lite_compute_transition_plan,
    lite_dense_animate_fallback_plan,
    lite_environments_system_prompt,
    lite_environments_user_message,
    lite_frame_generation_plans,
    lite_build_prev_line_animation_markup,
    lite_sanitize_animation_markup_for_i2v,
    lite_sanitize_i2v_text_prompt,
    lite_build_transition_system_prompt,
    lite_frames_from_montage_form_metadata,
    lite_frames_metadata_for_montage_form,
    lite_frames_system_prompt,
    lite_frames_user_message,
    lite_materialize_frame_results_inplace,
    lite_resolve_image_url_for_external_api,
    lite_run_step2_frames_with_prev_link,
    lite_effective_prompt_mode,
    lite_resolve_montage_preset,
    lite_transition_plan_with_selection,
    lite_transitions_kling_reference_system_prompt,
    lite_transitions_seedance_system_prompt,
    lite_transitions_system_prompt,
    lite_transitions_user_payload_dict,
    lite_transitions_wan26_system_prompt,
    lite_make_bases_bundle,
    lite_read_bases_bundle_from_json,
    run_lite_env_char_visual_chain,
    run_lite_frame_visual_chain,
    run_lite_i2v_concat_to_mp4,
    run_lite_visual_generation_chain,
    split_lite_step1_world,
)
from services.observability.workspaces import get_workspace_detail, list_workspace_summaries
from services.observability.beat_planner_diagnostics import (
    append_beat_planner_run,
    beat_planner_log_path,
    diff_last_two_runs,
)
from services.dreams.dream_orchestrator import DreamPipelineService, _actor_key
from services.dreams.dream_scene_planner import (
    _asset_ctx_short,
    _beat_planner_system_prompt,
    _image_prompts_system,
    _scenarist_system_prompt,
)
from services.dreams.models import DreamSceneOutline
from services.tools.image_tools import tool_edit_image, tool_generate_image
from services.tools import OPENAI_TOOLS_DEFAULT
from services.tools.openai_definitions import get_tools_for_runtime
from services.tools.openrouter_image_tools import (
    tool_generate_image_openrouter,
)
from services.tools.video_tools import tool_image_to_video
from services.video.openrouter_video_client import normalize_openrouter_video_model_id
from storage.chat_repository import ChatStoreRepository
from storage.dev_usage_ledger_repository import DevUsageLedgerRepository
from storage.dream_asset_repository import DreamAssetRepository
from storage.dream_lite_artifact_repository import DreamLiteArtifactRepository
from storage.dream_lite_step3_snapshot_repository import DreamLiteStep3SnapshotRepository
from storage.dream_lite_run_repository import DreamLiteRunRepository
from storage.dream_run_repository import DreamRunRepository
from storage.dream_scene_repository import DreamSceneRepository
from storage.generated_frame_repository import GeneratedFrameRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.scene_video_repository import SceneVideoRepository
from storage.story_video_repository import StoryVideoRepository
from storage.telegram_access_repository import TelegramAccessRepository
from storage.repository import MessageRepository


async def _dream_lite_materialize_playground_frames(
    frame_results: list[Any],
    artifact_repo: DreamLiteArtifactRepository | None,
) -> None:
    """Сохраняет data URI в /dev/static под user_id=0; опционально пишет метаданные в Mongo (TTL)."""
    rid = str(uuid.uuid4())
    lite_materialize_frame_results_inplace(
        list(frame_results),
        user_id=LITE_PLAYGROUND_USER_ID,
        lite_run_id=rid,
    )
    if artifact_repo is not None:
        await artifact_repo.record_frame_artifacts(
            user_id=LITE_PLAYGROUND_USER_ID,
            lite_run_id=rid,
            frame_results=list(frame_results),
        )
from storage.video_job_repository import VideoJobRepository

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.filters["tojson"] = lambda v, indent=2: Markup(
    json.dumps(
        v,
        ensure_ascii=False,
        indent=indent,
        default=str,
    )
)
_TEMPLATES.env.filters["dream_actor_key"] = lambda n: _actor_key(str(n or ""))
_STATIC = Path(__file__).parent / "static"

_UPLOAD_ID_RE = re.compile(r"^[a-f0-9]{32}\.[a-z0-9]+$", re.IGNORECASE)
_MONGO_CLIENT_SINGLETON: MongoClient | None = None

# Единый интервал polling dev UI (Messages, Dream Pipeline) — секунды для htmx `every Ns`
_DEV_POLL_INTERVAL_SEC = 2.5
_WAN26_VIDEO_MODEL_ID = "alibaba/wan-2.6"
_KLING_V3_STD_MODEL_ID = "kwaivgi/kling-v3.0-std"
_SIMPLE_MODE_RECOMMENDED_IMAGE_MODEL = "google/gemini-3-pro-image-preview"

_PLAYGROUND_FORM_IDS = frozenset(
    {"form-playground-qwen", "form-playground-openrouter"}
)
_PG_USER_BUTTON_SLOTS: dict[str, tuple[str, str]] = {
    "qwen": ("pg-qwen-asset-host", "form-playground-qwen"),
    "openrouter": ("pg-openrouter-asset-host", "form-playground-openrouter"),
}


def _tools_frame_with_model_picker(
    settings: Settings, ctx: dict[str, Any]
) -> dict[str, Any]:
    """Подмешивает в контекст Tools вкладки выбор модели Stage 0 и подпись «чат = nano»."""
    out = dict(ctx)
    out["dream_decompose_model_choices"] = settings.dream_decompose_model_options_list()
    out["default_dream_decompose_model"] = settings.openai_model_dream_decompose
    out["openai_model_label"] = settings.openai_model
    return out


def _upload_dir(settings: Settings) -> Path:
    return (settings.data_dir / "dev_uploads" / "video_inputs").resolve()


def _is_localhost(request: Request) -> bool:
    c = request.client
    if not c:
        return False
    host = c.host or ""
    if host in ("127.0.0.1", "::1", "localhost") or host.startswith("127."):
        return True
    try:
        ip = ip_address(host)
    except ValueError:
        return False
    # Allow private proxy hops (Docker bridge / local reverse proxy).
    return ip.is_private


def _dream_lite_openrouter_image_catalog() -> list[dict[str, Any]]:
    s = get_settings()
    return catalog_models_for_template(
        settings_default_id=s.openrouter_image_model or "",
        settings_fallback_id=s.openrouter_image_model_fallback or "",
    )


def _check_dev_basic_auth(request: Request, settings: Settings) -> bool:
    user = (settings.dev_debug_ui_username or "").strip()
    pwd = settings.dev_debug_ui_password or ""
    if not user:
        return True
    auth = (request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("basic "):
        return False
    token = auth[6:].strip()
    try:
        raw = base64.b64decode(token, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    if ":" not in raw:
        return False
    in_user, in_pwd = raw.split(":", 1)
    return hmac.compare_digest(in_user, user) and hmac.compare_digest(in_pwd, pwd)


def create_dev_console_router(
    settings: Settings,
    message_repo: MessageRepository,
    obs_repo: ObservabilityRepository,
    chat_store: ChatStoreRepository,
    dream_asset_repo: DreamAssetRepository,
    video_job_repo: VideoJobRepository,
    *,
    dream_run_repo: DreamRunRepository | None = None,
    dream_scene_repo: DreamSceneRepository | None = None,
    generated_frame_repo: GeneratedFrameRepository | None = None,
    generated_image_repo: GeneratedImageRepository | None = None,
    scene_video_repo: SceneVideoRepository | None = None,
    story_video_repo: StoryVideoRepository | None = None,
    dream_pipeline_service: DreamPipelineService | None = None,
    dev_usage_ledger_repo: DevUsageLedgerRepository | None = None,
    dream_lite_run_repo: DreamLiteRunRepository | None = None,
    dream_lite_artifact_repo: DreamLiteArtifactRepository | None = None,
    telegram_access_repo: TelegramAccessRepository | None = None,
    dream_lite_step3_snapshot_repo: DreamLiteStep3SnapshotRepository | None = None,
) -> APIRouter:
    def _parse_telegram_allowlist_text(raw: str) -> tuple[list[int], list[str]]:
        ids: list[int] = []
        bad: list[str] = []
        for token in re.split(r"[,\n;\s]+", str(raw or "").strip()):
            t = token.strip()
            if not t:
                continue
            try:
                ids.append(int(t))
            except Exception:
                bad.append(t)
        return sorted(set(ids)), bad

    def _current_telegram_access_policy() -> dict[str, Any]:
        enabled = bool(settings.telegram_access_allowlist_enabled)
        ids = sorted(settings.telegram_allowed_user_ids_set())
        updated_at = None
        updated_by = "env"
        if telegram_access_repo is not None:
            try:
                p = telegram_access_repo.get_policy_sync()
                enabled = bool(p.get("enabled", enabled))
                ids = sorted(set(int(x) for x in list(p.get("user_ids") or ids)))
                updated_at = p.get("updated_at")
                updated_by = str(p.get("updated_by") or "dev_console")
            except Exception:
                pass
        ids_text = "\n".join(str(x) for x in ids)
        return {
            "enabled": enabled,
            "user_ids": ids,
            "user_ids_text": ids_text,
            "updated_at": updated_at,
            "updated_by": updated_by,
        }

    def _step3_snapshot_payload(
        *,
        dream_text: str,
        environments_text: str,
        frames_text: str,
        frames_prev_link_raw: str,
        bases_bundle_json: str,
        frames_for_step4_json: list[dict[str, Any]],
        selected_image_model: str,
        simple_mode: bool,
    ) -> dict[str, Any]:
        return {
            "dream_text": str(dream_text or "").strip(),
            "environments_text": str(environments_text or "").strip(),
            "frames_text": str(frames_text or "").strip(),
            "frames_prev_link_raw": str(frames_prev_link_raw or "").strip(),
            "bases_bundle_json": str(bases_bundle_json or "").strip(),
            "frames_for_step4_json": list(frames_for_step4_json or []),
            "selected_image_model": str(selected_image_model or "").strip(),
            "simple_mode": bool(simple_mode),
        }

    def _load_step3_snapshot_sync() -> dict[str, Any] | None:
        if dream_lite_step3_snapshot_repo is None:
            return None
        try:
            return dream_lite_step3_snapshot_repo.get_latest_sync(
                user_id=int(settings.dream_lite_playground_user_id),
            )
        except Exception:
            return None

    def _tools_frame_ctx(**overrides: Any) -> dict[str, Any]:
        params: dict[str, Any] = {
            "data_dir": settings.data_dir,
            "chat_store": chat_store,
            "video_job_repo": video_job_repo,
            "dream_run_repo": dream_run_repo,
            "dream_scene_repo": dream_scene_repo,
            "generated_frame_repo": generated_frame_repo,
            "scene_video_repo": scene_video_repo,
            "story_video_repo": story_video_repo,
            "usage_ledger_repo": dev_usage_ledger_repo,
        }
        params.update(overrides)
        return build_tools_frame_context(**params)

    def _active_lite_steps_cfg() -> dict[str, Any]:
        base = default_run_config()
        base_steps = base.get("steps") if isinstance(base.get("steps"), dict) else {}
        if dream_lite_run_repo is None:
            return dict(base_steps)
        prof = dream_lite_run_repo.get_active_profile_sync() or {}
        cfg = prof.get("run_config") if isinstance(prof.get("run_config"), dict) else {}
        steps = cfg.get("steps") if isinstance(cfg.get("steps"), dict) else {}
        out = dict(base_steps)
        out.update({k: v for k, v in steps.items() if isinstance(k, str)})
        return out

    def _dream_lite_catalog_with_test_stats() -> list[dict[str, Any]]:
        catalog = [dict(x) for x in _dream_lite_openrouter_image_catalog()]
        for row in catalog:
            if not str(row.get("cost_hint") or "").strip():
                row["cost_hint"] = "Цена: см. каталог OpenRouter"
        if dream_lite_run_repo is None:
            return catalog
        stats: dict[str, dict[str, Any]] = {}
        try:
            recent = dream_lite_run_repo.list_recent_runs_sync(limit=180)
        except Exception:
            recent = []
        for run in recent:
            trace = list(run.get("execution_trace") or [])
            for ev in trace:
                if not isinstance(ev, dict):
                    continue
                if str(ev.get("event") or "") != "image_frame_generated":
                    continue
                model = str(ev.get("model") or "").strip()
                if not model:
                    continue
                row = stats.setdefault(
                    model,
                    {"runs_count": 0, "ok_count": 0, "fail_count": 0, "last_tested_at": "", "samples": []},
                )
                row["runs_count"] = int(row["runs_count"]) + 1
                if bool(ev.get("ok")):
                    row["ok_count"] = int(row["ok_count"]) + 1
                else:
                    row["fail_count"] = int(row["fail_count"]) + 1
                ts = ev.get("ts")
                ts_s = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")
                if ts_s and ts_s > str(row["last_tested_at"] or ""):
                    row["last_tested_at"] = ts_s
                row["samples"].append(
                    {
                        "ts": ts_s,
                        "duration_ms": int(ev.get("duration_ms") or 0),
                        "provider_latency_ms": int(ev.get("provider_latency_ms") or 0),
                        "tokens_in": int(ev.get("tokens_in") or 0),
                        "tokens_out": int(ev.get("tokens_out") or 0),
                        "total_tokens": int(ev.get("total_tokens") or 0),
                    }
                )
            for fr in list(run.get("generated_frames") or []):
                if not isinstance(fr, dict):
                    continue
                model = str(fr.get("effective_model") or fr.get("image_model") or "").strip()
                if not model:
                    continue
                row = stats.setdefault(
                    model,
                    {"runs_count": 0, "ok_count": 0, "fail_count": 0, "last_tested_at": "", "samples": []},
                )
                row["runs_count"] = int(row["runs_count"]) + 1
                if bool(fr.get("ok")):
                    row["ok_count"] = int(row["ok_count"]) + 1
                else:
                    row["fail_count"] = int(row["fail_count"]) + 1
                ts_raw = fr.get("completed_at") or fr.get("request_at") or run.get("updated_at")
                ts_s = ts_raw.isoformat() if hasattr(ts_raw, "isoformat") else str(ts_raw or "")
                if ts_s and ts_s > str(row["last_tested_at"] or ""):
                    row["last_tested_at"] = ts_s
                row["samples"].append(
                    {
                        "ts": ts_s,
                        "duration_ms": int(fr.get("duration_ms") or 0),
                        "provider_latency_ms": int(fr.get("provider_latency_ms") or 0),
                        "tokens_in": int(fr.get("tokens_in") or 0),
                        "tokens_out": int(fr.get("tokens_out") or 0),
                        "total_tokens": int(fr.get("total_tokens") or 0),
                    }
                )
        for item in catalog:
            mid = str(item.get("id") or "")
            s = stats.get(mid) or {}
            runs_count = int(s.get("runs_count") or 0)
            ok_count = int(s.get("ok_count") or 0)
            fail_count = int(s.get("fail_count") or 0)
            tested_status = "untested"
            if runs_count > 0 and ok_count > 0 and fail_count == 0:
                tested_status = "tested_success"
            elif runs_count > 0 and ok_count > 0 and fail_count > 0:
                tested_status = "tested_with_fallback"
            elif runs_count > 0 and ok_count == 0:
                tested_status = "tested_failed_only"
            item["tested"] = runs_count > 0
            item["runs_count"] = runs_count
            item["last_tested_at"] = str(s.get("last_tested_at") or "")
            item["tested_status"] = tested_status
            item["samples"] = list(s.get("samples") or [])
        return catalog

    def _active_lite_video_policy() -> dict[str, Any]:
        base = default_run_config()
        base_policy = base.get("video_policy") if isinstance(base.get("video_policy"), dict) else {}
        if dream_lite_run_repo is None:
            out0 = dict(base_policy)
            out0["openrouter_model"] = normalize_openrouter_video_model_id(out0.get("openrouter_model"))
            return out0
        prof = dream_lite_run_repo.get_active_profile_sync() or {}
        cfg = prof.get("run_config") if isinstance(prof.get("run_config"), dict) else {}
        policy = cfg.get("video_policy") if isinstance(cfg.get("video_policy"), dict) else {}
        out = dict(base_policy)
        out.update({k: v for k, v in policy.items() if isinstance(k, str)})
        out["openrouter_model"] = normalize_openrouter_video_model_id(out.get("openrouter_model"))
        return out

    def _is_seedance_audio_locked(video_policy: dict[str, Any]) -> bool:
        mp = str((video_policy or {}).get("montage_preset") or "").strip().lower()
        audio_req = bool((video_policy or {}).get("audio_required"))
        return mp == "seedance" and audio_req

    def _is_kling_reference_preset(video_policy: dict[str, Any]) -> bool:
        mp = str((video_policy or {}).get("montage_preset") or "").strip().lower()
        return mp == "kling_v3_reference_motion"

    def _effective_video_prompt_policy(
        *,
        prompt_mode: str,
        montage_preset: str,
        audio_required: bool,
    ) -> tuple[str, str, bool]:
        return lite_effective_prompt_mode(
            prompt_mode=prompt_mode,
            montage_preset=montage_preset,
            audio_required=audio_required,
        )

    def _validate_video_mode_model(prompt_mode: str, model_id: str, *, audio_required: bool = False) -> tuple[bool, str]:
        pm = (prompt_mode or "first_last_frame").strip() or "first_last_frame"
        if pm not in {"first_last_frame", "first_frame_only", "text_only"}:
            return False, f"unsupported prompt_mode={pm}"
        prof = get_video_model_profile(model_id)
        if not prof:
            return False, "video model profile not found"
        ok, reason = video_model_mode_compatible(prof, pm)
        if ok and audio_required:
            audio_mode = str(prof.get("audio_mode") or "unknown")
            if audio_mode == "silent_only":
                return False, "audio_required but selected model is silent_only"
        return ok, reason

    def _normalize_video_resolution_value(resolution: str, *, profile: dict[str, Any] | None = None) -> str:
        raw = str(resolution or "").strip()
        if not raw:
            raw = "720p"
        low = raw.lower()
        alias_map = {
            "480x480": "480p",
            "720x720": "720p",
            "1080x1080": "1080p",
        }
        normalized = alias_map.get(low, raw)
        supported: list[str] = []
        if isinstance(profile, dict):
            limits = profile.get("limits")
            if isinstance(limits, dict):
                for x in list(limits.get("supported_resolutions") or []):
                    sx = str(x or "").strip()
                    if sx:
                        supported.append(sx)
        if not supported:
            return normalized
        if normalized in supported:
            return normalized
        norm_low = normalized.lower()
        for s in supported:
            if s.lower() == norm_low:
                return s
        # fallback to first supported value to avoid provider 400
        return supported[0]

    def _is_first_frame_stable_model(model_id: str) -> bool:
        mid = normalize_openrouter_video_model_id(model_id)
        return mid in {"kwaivgi/kling-v3.0-std"}

    def _resolve_i2v_payload_url(raw_url: str, *, allow_empty: bool = True) -> str:
        u = str(raw_url or "").strip()
        if not u:
            return ""
        resolved = lite_resolve_image_url_for_external_api(u)
        if resolved and resolved != u:
            return resolved
        if u.startswith("/dev/static/"):
            base = str(get_settings().public_base_url or "").strip().rstrip("/")
            if base:
                return f"{base}{u}"
            if allow_empty:
                return ""
        return resolved or u

    def _clamp_i2v_duration_sec(
        raw: Any,
        *,
        profile: dict[str, Any] | None = None,
        model_id: str | None = None,
        default_value: int = 4,
    ) -> int:
        try:
            d = int(raw)
        except Exception:
            d = int(default_value)
        mid = normalize_openrouter_video_model_id(
            model_id or (str(profile.get("model_id") or "") if isinstance(profile, dict) else "")
        )
        if mid == "alibaba/wan-2.6":
            return 5
        d = max(1, min(d, 6))
        supported: list[int] = []
        if isinstance(profile, dict):
            limits = profile.get("limits")
            if isinstance(limits, dict):
                for v in list(limits.get("supported_durations") or []):
                    try:
                        iv = int(v)
                    except Exception:
                        continue
                    if iv > 0:
                        supported.append(iv)
        if not supported:
            return d
        allowed = [x for x in supported if x <= 6]
        if allowed:
            return min(allowed, key=lambda x: abs(x - d))
        return min(supported)

    def _normalize_markup_provider_duration(
        animation_markup: dict[str, Any] | None,
        *,
        model_id: str,
        default_duration: int,
    ) -> dict[str, Any]:
        if not isinstance(animation_markup, dict):
            return {}
        out = dict(animation_markup)
        lines_out: list[dict[str, Any]] = []
        for line in list(out.get("lines") or []):
            if not isinstance(line, dict):
                continue
            line_copy = dict(line)
            segs_out: list[dict[str, Any]] = []
            for seg in list(line.get("segments") or []):
                if not isinstance(seg, dict):
                    continue
                s = dict(seg)
                payload = dict(s.get("api_payload_preview") or {}) if isinstance(s.get("api_payload_preview"), dict) else {}
                calc_raw = (
                    s.get("calculated_duration_sec")
                    or payload.get("calculated_duration_sec")
                    or s.get("duration_sec")
                    or payload.get("duration_sec")
                    or default_duration
                )
                calculated = _clamp_i2v_duration_sec(calc_raw, model_id=model_id, default_value=default_duration)
                provider = _clamp_i2v_duration_sec(calculated, model_id=model_id, default_value=default_duration)
                s["calculated_duration_sec"] = int(calculated)
                s["provider_duration_sec"] = int(provider)
                s["duration_sec"] = int(provider)
                payload["calculated_duration_sec"] = int(calculated)
                payload["provider_duration_sec"] = int(provider)
                payload["duration_sec"] = int(provider)
                s["api_payload_preview"] = payload
                segs_out.append(s)
            line_copy["segments"] = segs_out
            lines_out.append(line_copy)
        out["lines"] = lines_out
        return out

    def _mongo_sync_collection(name: str) -> Any | None:
        global _MONGO_CLIENT_SINGLETON
        try:
            if _MONGO_CLIENT_SINGLETON is None:
                _MONGO_CLIENT_SINGLETON = MongoClient(settings.mongodb_uri)
            return _MONGO_CLIENT_SINGLETON[settings.mongodb_db][name]
        except Exception:
            return None

    async def _upsert_active_profile_video_policy(
        *,
        backend: str | None = None,
        i2v_model: str | None = None,
        duration_sec: int | None = None,
        resolution: str | None = None,
        openrouter_model: str | None = None,
        prompt_mode: str | None = None,
        montage_preset: str | None = None,
        audio_required: bool | None = None,
        scene_segment_stride: int | None = None,
        reference_frame_stride: int | None = None,
        require_montage_confirm: bool | None = None,
    ) -> None:
        if dream_lite_run_repo is None:
            return
        prof = dream_lite_run_repo.get_active_profile_sync() or {}
        cfg = prof.get("run_config") if isinstance(prof.get("run_config"), dict) else default_run_config()
        cfg_copy = dict(cfg)
        vp = cfg_copy.get("video_policy") if isinstance(cfg_copy.get("video_policy"), dict) else {}
        vp2 = dict(vp)
        vp2["openrouter_model"] = normalize_openrouter_video_model_id(vp2.get("openrouter_model"))
        if backend is not None:
            vp2["backend"] = str(backend or "").strip()
        if i2v_model is not None:
            vp2["i2v_model"] = str(i2v_model or "").strip()
        if openrouter_model is not None:
            vp2["openrouter_model"] = normalize_openrouter_video_model_id(openrouter_model)
        if prompt_mode is not None:
            pm = str(prompt_mode or "").strip() or "first_last_frame"
            if pm not in {"first_frame_only", "text_only", "first_last_frame"}:
                pm = "first_last_frame"
            vp2["prompt_mode"] = pm
        if montage_preset is not None:
            mp = str(montage_preset or "").strip().lower() or "default"
            if mp not in {"default", "seedance", "wan_2_6_single_anchor", "kling_v3_reference_motion"}:
                mp = "default"
            vp2["montage_preset"] = mp
        if audio_required is not None:
            vp2["audio_required"] = bool(audio_required)
        if duration_sec is not None:
            try:
                vp2["duration_sec"] = max(1, int(duration_sec))
            except Exception:
                pass
        if resolution is not None:
            vp2["resolution"] = str(resolution or "").strip() or "720p"
        if scene_segment_stride is not None:
            try:
                vp2["scene_segment_stride"] = max(1, int(scene_segment_stride))
            except Exception:
                pass
        if reference_frame_stride is not None:
            try:
                vp2["reference_frame_stride"] = max(1, int(reference_frame_stride))
            except Exception:
                pass
        if require_montage_confirm is not None:
            vp2["require_montage_confirm"] = bool(require_montage_confirm)
        cfg_copy["video_policy"] = vp2
        await dream_lite_run_repo.upsert_active_profile(
            run_config=cfg_copy,
            pipeline_variant=str(cfg_copy.get("pipeline_variant") or "").strip() or None,
            updated_by_user_id=int(settings.dream_lite_playground_user_id),
            profile_name=str(prof.get("profile_name") or "default").strip() or "default",
        )

    def _dream_lite_video_catalog_with_stats() -> list[dict[str, Any]]:
        catalog = [dict(x) for x in video_model_capability_registry()]
        if dream_lite_run_repo is None:
            return catalog
        stats: dict[str, dict[str, Any]] = {}
        try:
            recent = dream_lite_run_repo.list_recent_runs_sync(limit=180)
        except Exception:
            recent = []
        for run in recent:
            for ev in list(run.get("execution_trace") or []):
                if not isinstance(ev, dict) or str(ev.get("event") or "") != "i2v_segment_created":
                    continue
                model = str(ev.get("model") or "").strip() or "wan2.7-i2v"
                row = stats.setdefault(model, {"runs_count": 0, "ok_count": 0, "fail_count": 0, "samples": [], "last_tested_at": ""})
                row["runs_count"] = int(row["runs_count"]) + 1
                row["ok_count"] = int(row["ok_count"]) + (1 if bool(ev.get("ok")) else 0)
                row["fail_count"] = int(row["fail_count"]) + (0 if bool(ev.get("ok")) else 1)
                ts = ev.get("ts")
                ts_s = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")
                if ts_s and ts_s > str(row["last_tested_at"] or ""):
                    row["last_tested_at"] = ts_s
                row["samples"].append(
                    {
                        "ts": ts_s,
                        "duration_ms": int(ev.get("duration_ms") or 0),
                        "provider_latency_ms": int(ev.get("provider_latency_ms") or 0),
                        "tokens_in": int(ev.get("tokens_in") or 0),
                        "tokens_out": int(ev.get("tokens_out") or 0),
                        "total_tokens": int(ev.get("total_tokens") or 0),
                    }
                )
        # Primary source: persistent metrics collection (survives container restarts).
        coll = _mongo_sync_collection("dream_lite_generation_metrics")
        if coll is not None:
            try:
                rows = list(coll.find({"stage": "anim_i2v"}, {"_id": 0}).sort("created_at", -1).limit(1200))
            except Exception:
                rows = []
            for ev in rows:
                model = str(ev.get("model_id") or ev.get("effective_model") or ev.get("requested_model") or "").strip() or "wan2.7-i2v"
                row = stats.setdefault(model, {"runs_count": 0, "ok_count": 0, "fail_count": 0, "samples": [], "last_tested_at": ""})
                # Для метрик без explicit ok считаем как успешную выборку времени, если duration/latency > 0.
                dur = int(ev.get("duration_ms") or 0)
                lat = int(ev.get("provider_latency_ms") or 0)
                looks_ok = dur > 0 or lat > 0
                row["runs_count"] = int(row["runs_count"]) + 1
                row["ok_count"] = int(row["ok_count"]) + (1 if looks_ok else 0)
                row["fail_count"] = int(row["fail_count"]) + (0 if looks_ok else 1)
                ts = ev.get("completed_at") or ev.get("created_at")
                ts_s = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")
                if ts_s and ts_s > str(row["last_tested_at"] or ""):
                    row["last_tested_at"] = ts_s
                row["samples"].append(
                    {
                        "ts": ts_s,
                        "duration_ms": dur,
                        "provider_latency_ms": lat,
                        "tokens_in": int(ev.get("tokens_in") or 0),
                        "tokens_out": int(ev.get("tokens_out") or 0),
                        "total_tokens": int(ev.get("total_tokens") or 0),
                    }
                )
        for item in catalog:
            mid = str(item.get("model_id") or "")
            item["supported_prompt_modes"] = list(item.get("supported_prompt_modes") or video_model_supported_prompt_modes(item))
            s = stats.get(mid) or {}
            runs_count = int(s.get("runs_count") or 0)
            ok_count = int(s.get("ok_count") or 0)
            fail_count = int(s.get("fail_count") or 0)
            tested_status = "untested"
            if runs_count > 0 and ok_count > 0 and fail_count == 0:
                tested_status = "tested_success"
            elif runs_count > 0 and ok_count > 0 and fail_count > 0:
                tested_status = "tested_with_fallback"
            elif runs_count > 0 and ok_count == 0:
                tested_status = "tested_failed_only"
            item["tested"] = runs_count > 0
            item["tested_status"] = tested_status
            item["runs_count"] = runs_count
            item["last_tested_at"] = str(s.get("last_tested_at") or "")
            item["samples"] = list(s.get("samples") or [])
        return catalog

    def _video_model_insight_from_catalog(catalog: list[dict[str, Any]], model_id: str, *, last_n: int = 5) -> dict[str, Any]:
        mid = (model_id or "").strip()
        row = next((x for x in catalog if str(x.get("model_id") or "").strip() == mid), None) or {}
        samples = sorted(list(row.get("samples") or []), key=lambda x: str(x.get("ts") or ""), reverse=True)[: max(1, int(last_n))]

        def _avg_int(key: str, *, only_positive: bool = False) -> int | None:
            vals = []
            for s in samples:
                v = int((s or {}).get(key) or 0)
                if only_positive and v <= 0:
                    continue
                vals.append(v)
            if not vals:
                return None
            return int(sum(vals) / len(vals))

        avg_total = _avg_int("total_tokens", only_positive=True)
        return {
            "model_id": mid,
            "provider": str(row.get("provider") or ""),
            "quality_status": "tested" if bool(row.get("tested")) else "no_data_yet",
            "tested_status": str(row.get("tested_status") or "untested"),
            "runs_count": int(row.get("runs_count") or 0),
            "samples_count": len(samples),
            "avg_duration_ms_last_n": _avg_int("duration_ms", only_positive=True),
            "avg_provider_latency_ms_last_n": _avg_int("provider_latency_ms", only_positive=True),
            "avg_tokens_in_last_n": _avg_int("tokens_in", only_positive=True),
            "avg_tokens_out_last_n": _avg_int("tokens_out", only_positive=True),
            "avg_total_tokens_last_n": avg_total,
            "usage_unavailable": avg_total is None,
            "refs_quality_level": str(row.get("refs_quality_level") or "no_data_yet"),
            "refs_quality_note": str(row.get("refs_quality_note") or "Not tested yet"),
            "degraded_reason": str(row.get("degraded_reason") or ""),
        }

    def _resolve_refs_quality_for_model(model_id: str, tested: bool) -> tuple[str, str]:
        prof = get_model_profile(model_id) or {}
        lvl = str(prof.get("refs_quality_level") or "").strip()
        note = str(prof.get("refs_quality_note") or "").strip()
        if lvl and note:
            return lvl, note
        if tested:
            return (
                "limited",
                "По логам модель тестировалась, но качество привязки character refs может плавать от кадра к кадру.",
            )
        return "no_data_yet", "Not tested yet"

    def _model_insight_from_catalog(catalog: list[dict[str, Any]], model_id: str, *, last_n: int = 5) -> dict[str, Any]:
        mid = (model_id or "").strip()
        row = next((x for x in catalog if str(x.get("id") or "").strip() == mid), None) or {}
        samples = sorted(list(row.get("samples") or []), key=lambda x: str(x.get("ts") or ""), reverse=True)[: max(1, int(last_n))]
        tested = bool(row.get("tested"))
        refs_level, refs_note = _resolve_refs_quality_for_model(mid, tested)

        def _avg_int(key: str, *, only_positive: bool = False) -> int | None:
            vals = []
            for s in samples:
                v = int((s or {}).get(key) or 0)
                if only_positive and v <= 0:
                    continue
                vals.append(v)
            if not vals:
                return None
            return int(sum(vals) / len(vals))

        avg_duration = _avg_int("duration_ms")
        avg_latency = _avg_int("provider_latency_ms")
        avg_in = _avg_int("tokens_in", only_positive=True)
        avg_out = _avg_int("tokens_out", only_positive=True)
        avg_total = _avg_int("total_tokens", only_positive=True)
        usage_unavailable = avg_total is None
        return {
            "model_id": mid,
            "model_label": str(row.get("label") or mid),
            "quality_status": "tested" if tested else "no_data_yet",
            "refs_quality_level": refs_level,
            "refs_quality_note": refs_note,
            "samples_count": len(samples),
            "avg_duration_ms_last_n": avg_duration,
            "avg_provider_latency_ms_last_n": avg_latency,
            "avg_tokens_in_last_n": avg_in,
            "avg_tokens_out_last_n": avg_out,
            "avg_total_tokens_last_n": avg_total,
            "usage_unavailable": usage_unavailable,
            "tested_status": str(row.get("tested_status") or "untested"),
            "runs_count": int(row.get("runs_count") or 0),
        }

    async def _upsert_active_profile_step_prompt(step_key: str, prompt_text: str) -> None:
        if dream_lite_run_repo is None:
            return
        prof = dream_lite_run_repo.get_active_profile_sync() or {}
        cfg = prof.get("run_config") if isinstance(prof.get("run_config"), dict) else default_run_config()
        cfg_copy = dict(cfg)
        steps = cfg_copy.get("steps") if isinstance(cfg_copy.get("steps"), dict) else {}
        steps2 = dict(steps)
        steps2[step_key] = str(prompt_text or "")
        cfg_copy["steps"] = steps2
        await dream_lite_run_repo.upsert_active_profile(
            run_config=cfg_copy,
            pipeline_variant=str(cfg_copy.get("pipeline_variant") or "").strip() or None,
            updated_by_user_id=int(settings.dream_lite_playground_user_id),
            profile_name=str(prof.get("profile_name") or "default").strip() or "default",
        )

    async def _upsert_active_profile_image_policy(
        *,
        image_model: str | None = None,
        simple_mode: bool | None = None,
    ) -> None:
        if dream_lite_run_repo is None:
            return
        mid = (image_model or "").strip()
        prof = dream_lite_run_repo.get_active_profile_sync() or {}
        cfg = prof.get("run_config") if isinstance(prof.get("run_config"), dict) else default_run_config()
        cfg_copy = dict(cfg)
        img = cfg_copy.get("image_policy") if isinstance(cfg_copy.get("image_policy"), dict) else {}
        img2 = dict(img)
        if mid:
            img2["model"] = mid
        if simple_mode is not None:
            img2["simple_mode"] = bool(simple_mode)
        if not img2:
            return
        cfg_copy["image_policy"] = img2
        await dream_lite_run_repo.upsert_active_profile(
            run_config=cfg_copy,
            pipeline_variant=str(cfg_copy.get("pipeline_variant") or "").strip() or None,
            updated_by_user_id=int(settings.dream_lite_playground_user_id),
            profile_name=str(prof.get("profile_name") or "default").strip() or "default",
        )

    async def _upsert_active_profile_image_model(image_model: str) -> None:
        await _upsert_active_profile_image_policy(image_model=image_model, simple_mode=None)

    async def _guard(request: Request) -> None:
        if not settings.dev_debug_ui_enabled:
            raise HTTPException(status_code=404, detail="Dev console disabled")
        if (not settings.dev_debug_ui_allow_remote) and (not _is_localhost(request)):
            raise HTTPException(
                status_code=403,
                detail="Dev console only from localhost",
            )
        if not _check_dev_basic_auth(request, settings):
            raise HTTPException(
                status_code=401,
                detail="Dev console auth required",
                headers={"WWW-Authenticate": 'Basic realm="Dream Dev Console"'},
            )

    router = APIRouter(
        prefix="/dev",
        tags=["dev-console"],
        dependencies=[Depends(_guard)],
    )

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Any:
        css = _STATIC / "dev.css"
        js = _STATIC / "dev_ui.js"
        assets_version = int(
            max(
                css.stat().st_mtime if css.exists() else 0,
                js.stat().st_mtime if js.exists() else 0,
            )
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "title": "Dream Viz — Dev",
                "poll_interval_sec": _DEV_POLL_INTERVAL_SEC,
                "assets_version": assets_version,
            },
        )

    @router.get("/partials/messages/rows", response_class=HTMLResponse)
    async def partial_message_rows(request: Request) -> Any:
        items = get_recent_messages(message_repo, obs_repo, limit=150)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/message_rows.html",
            {"messages": items},
        )

    @router.post("/api/messages/clear", response_class=HTMLResponse)
    async def api_clear_messages(
        request: Request,
        scope: str = Form(...),
    ) -> Any:
        s = (scope or "").strip().lower()
        if s == "messages":
            await message_repo.delete_all_messages()
        elif s == "all":
            await message_repo.delete_all_messages()
            await obs_repo.delete_all_events()
            await chat_store.delete_all()
        else:
            raise HTTPException(status_code=400, detail="scope must be messages or all")
        items = get_recent_messages(message_repo, obs_repo, limit=150)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/messages_cleared_oob.html",
            {"messages": items},
        )

    @router.get("/partials/alpha_access/tab", response_class=HTMLResponse)
    async def partial_alpha_access_tab(request: Request) -> Any:
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/alpha_access_tab.html",
            {
                "policy": _current_telegram_access_policy(),
                "saved": False,
                "errors": [],
            },
        )

    @router.post("/api/alpha_access/save", response_class=HTMLResponse)
    async def api_alpha_access_save(
        request: Request,
        enabled: str = Form(""),
        user_ids: str = Form(""),
    ) -> Any:
        if telegram_access_repo is None:
            raise HTTPException(status_code=503, detail="telegram access repository not configured")
        enabled_flag = str(enabled or "").strip().lower() in {"1", "true", "on", "yes"}
        ids, bad = _parse_telegram_allowlist_text(user_ids)
        if enabled_flag and not ids:
            bad.append("Список user_id пуст при включённом allowlist")
        if bad:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/alpha_access_tab.html",
                {
                    "policy": {
                        "enabled": enabled_flag,
                        "user_ids": ids,
                        "user_ids_text": str(user_ids or "").strip(),
                        "updated_at": None,
                        "updated_by": "not_saved",
                    },
                    "saved": False,
                    "errors": [str(x) for x in bad],
                },
                status_code=400,
            )
        telegram_access_repo.upsert_policy_sync(
            enabled=enabled_flag,
            user_ids=ids,
            updated_by="dev_console",
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/alpha_access_tab.html",
            {
                "policy": _current_telegram_access_policy(),
                "saved": True,
                "errors": [],
            },
        )

    @router.get("/partials/workspaces/list", response_class=HTMLResponse)
    async def partial_workspace_list(
        request: Request,
        period: str = Query("all"),
        sort_by: str = Query("last_activity"),
        search: str = Query(""),
        custom_start: str | None = Query(None),
        custom_end: str | None = Query(None),
    ) -> Any:
        items = list_workspace_summaries(
            message_repo,
            chat_store,
            dream_asset_repo,
            video_job_repo,
            dream_run_repo,
            generated_frame_repo,
            generated_image_repo,
            scene_video_repo,
            story_video_repo,
            period=period,
            sort_by=sort_by,
            search=search,
            custom_start=custom_start,
            custom_end=custom_end,
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/workspaces_list.html",
            {
                "items": items,
                "period": period,
                "sort_by": sort_by,
                "search": search,
                "custom_start": custom_start or "",
                "custom_end": custom_end or "",
            },
        )

    @router.get("/partials/workspaces/{user_id}/detail", response_class=HTMLResponse)
    async def partial_workspace_detail(
        request: Request,
        user_id: int,
    ) -> Any:
        detail = get_workspace_detail(
            user_id,
            message_repo,
            chat_store,
            dream_asset_repo,
            video_job_repo,
            dream_run_repo,
            generated_frame_repo,
            generated_image_repo,
            scene_video_repo,
            story_video_repo,
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/workspace_detail.html",
            {"detail": detail},
        )

    @router.get("/partials/tools/frame", response_class=HTMLResponse)
    async def partial_tools_frame(
        request: Request,
        period: str = Query("month"),
        custom_start: str | None = Query(None),
        custom_end: str | None = Query(None),
        registry_view: str = Query("grid"),
        exec_tool: str | None = Query(None),
        exec_status: str | None = Query(None),
        exec_user: str | None = Query(None),
        only_errors: bool = Query(False),
        pipeline_job_id: str | None = Query(None),
    ) -> Any:
        ctx = _tools_frame_ctx(
            period=period,
            custom_start=custom_start,
            custom_end=custom_end,
            registry_view=registry_view,
            exec_tool=(exec_tool or "").strip() or None,
            exec_status=(exec_status or "").strip() or None,
            exec_user=(exec_user or "").strip() or None,
            only_errors=only_errors,
            pipeline_job_id=(pipeline_job_id or "").strip() or None,
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/tools_frame_agent_control.html",
            _tools_frame_with_model_picker(settings, ctx),
        )

    @router.post("/api/tools/playground/run", response_class=HTMLResponse)
    async def api_tools_playground_run(
        request: Request,
        tool_name: str = Form(...),
        arguments_json: str = Form("{}"),
    ) -> Any:
        tool = (tool_name or "").strip()
        raw = (arguments_json or "{}").strip() or "{}"
        started = time.perf_counter()
        status = "failed"
        error = ""
        req_obj: dict[str, Any] = {"tool_name": tool, "arguments": raw}
        resp_obj: Any = {}
        try:
            args_obj = json.loads(raw)
            req_obj["arguments"] = args_obj
            if not isinstance(args_obj, dict):
                raise ValueError("arguments_must_be_json_object")
            if tool == "generate_image":
                result = tool_generate_image(
                    prompt=str(args_obj.get("prompt") or "").strip(),
                    size=str(args_obj.get("size") or "1024*1536"),
                    model=str(args_obj.get("model") or "qwen-image-2.0"),
                    n=int(args_obj.get("n") or 1),
                )
                resp_obj = result.to_dict()
                status = "completed" if result.ok else "failed"
                if not result.ok:
                    error = result.error or ""
            elif tool == "generate_image_openrouter":
                _m = args_obj.get("model")
                _refs = args_obj.get("reference_image_urls")
                ref_list: list[str] | None = None
                if isinstance(_refs, list):
                    ref_list = [str(x).strip() for x in _refs if str(x).strip()]
                    if not ref_list:
                        ref_list = None
                elif isinstance(_refs, str) and _refs.strip():
                    ref_list = [_refs.strip()]
                result = tool_generate_image_openrouter(
                    str(args_obj.get("prompt") or "").strip(),
                    aspect_ratio=str(args_obj["aspect_ratio"]).strip()
                    if args_obj.get("aspect_ratio")
                    else None,
                    image_size=str(args_obj["image_size"]).strip()
                    if args_obj.get("image_size")
                    else None,
                    model=str(_m).strip() if _m else None,
                    reference_image_urls=ref_list,
                )
                resp_obj = result.to_dict()
                status = "completed" if result.ok else "failed"
                if not result.ok:
                    error = result.error or ""
            elif tool == "image_to_video":
                _lf = args_obj.get("last_frame_url")
                result = tool_image_to_video(
                    prompt=str(args_obj.get("prompt") or "").strip(),
                    image_url=str(args_obj.get("image_url") or "").strip(),
                    model=str(args_obj.get("model") or "wan2.7-i2v"),
                    duration=int(args_obj.get("duration") or 4),
                    resolution=str(args_obj.get("resolution") or "720p"),
                    owner_user_id=str(args_obj.get("owner_user_id") or "dev_playground"),
                    last_frame_url=str(_lf).strip() if _lf else None,
                )
                resp_obj = result
                status = "completed" if result.get("ok") else "failed"
                if not result.get("ok"):
                    error = str(result.get("error") or "")
            else:
                status = "failed"
                error = f"unsupported_tool: {tool}"
                resp_obj = {"ok": False, "error": error}
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error = str(exc)
            resp_obj = {"ok": False, "error": error}

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        args_saved = req_obj.get("arguments")
        args_dict = args_saved if isinstance(args_saved, dict) else {}
        try:
            if tool == "generate_image":
                record_dev_usage(
                    dev_usage_ledger_repo,
                    category="image",
                    provider="dashscope",
                    model=str(args_dict.get("model") or "qwen-image-2.0"),
                    source="dev.tools.playground",
                    meta={"latency_ms": elapsed_ms},
                    ok=(status == "completed"),
                )
            elif tool == "generate_image_openrouter":
                usage_raw = (
                    resp_obj.get("usage")
                    if isinstance(resp_obj, dict)
                    else None
                )
                inp, outp, tot, cost = normalize_openrouter_usage(usage_raw)
                _om = args_dict.get("model")
                record_dev_usage(
                    dev_usage_ledger_repo,
                    category="image_openrouter",
                    provider="openrouter",
                    model=str(_om).strip() if _om else None,
                    source="dev.tools.playground",
                    input_tokens=inp,
                    output_tokens=outp,
                    total_tokens=tot,
                    cost_usd=cost,
                    meta={"latency_ms": elapsed_ms},
                    ok=(status == "completed"),
                )
            elif tool == "image_to_video":
                record_dev_usage(
                    dev_usage_ledger_repo,
                    category="video",
                    provider="wan",
                    model=str(args_dict.get("model") or "wan2.7-i2v"),
                    source="dev.tools.playground",
                    meta={
                        "latency_ms": elapsed_ms,
                        "job_id": resp_obj.get("job_id")
                        if isinstance(resp_obj, dict)
                        else None,
                    },
                    ok=(status == "completed"),
                )
        except Exception:  # noqa: BLE001
            pass

        return _TEMPLATES.TemplateResponse(
            request,
            "partials/tools_playground_result.html",
            {
                "status": status,
                "error": error,
                "latency_ms": elapsed_ms,
                "raw_request": req_obj,
                "raw_response": resp_obj,
            },
        )

    @router.post("/api/pipeline/run", response_class=HTMLResponse)
    async def api_pipeline_run(
        request: Request,
        user_id: str = Form(...),
        dream_text: str = Form(...),
        chat_id: str = Form(""),
        decompose_model: str = Form(""),
    ) -> Any:
        if dream_pipeline_service is None:
            return HTMLResponse(
                '<p class="muted" style="color:#ff7b72">Dream pipeline service не подключён.</p>',
                status_code=400,
            )
        try:
            uid = int((user_id or "").strip())
        except Exception:
            return HTMLResponse(
                '<p class="muted" style="color:#ff7b72">Некорректный user_id.</p>',
                status_code=400,
            )
        text = (dream_text or "").strip()
        if not text:
            return HTMLResponse(
                '<p class="muted" style="color:#ff7b72">Пустой dream_text.</p>',
                status_code=400,
            )
        dm = (decompose_model or "").strip() or None
        if dm and dm not in settings.dream_decompose_model_options_list():
            return HTMLResponse(
                '<p class="muted" style="color:#ff7b72">Недопустимая модель Stage 0.</p>',
                status_code=400,
            )
        cid = None
        if (chat_id or "").strip():
            try:
                cid = int(chat_id.strip())
            except Exception:
                cid = None
        run_id = await dream_pipeline_service.run_from_dev(
            user_id=uid,
            dream_text=text,
            chat_id=cid,
            decompose_model=dm,
        )
        if not run_id:
            return HTMLResponse(
                '<p class="muted" style="color:#ff7b72">Не удалось создать run.</p>',
                status_code=500,
            )
        return HTMLResponse(
            f'<p class="muted" style="color:#56d364">Pipeline запущен: <code>{html.escape(run_id)}</code></p>'
        )

    @router.get("/partials/prompts/editor", response_class=HTMLResponse)
    async def partial_prompts_editor(request: Request) -> Any:
        try:
            system_content = read_system_prompt_raw()
        except SystemPromptError as e:
            system_content = f"# Ошибка чтения system_prompt.md: {e}\n"
        global_content = read_global_model_policy_raw()
        dream_image_content = read_dream_image_prompts_raw()
        dream_intent_content = read_dream_intent_routing_raw()
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/prompts_editor.html",
            {
                "system_content": system_content,
                "global_content": global_content,
                "dream_image_content": dream_image_content,
                "dream_intent_content": dream_intent_content,
            },
        )

    @router.post("/api/prompts/system-md", response_class=HTMLResponse)
    async def api_save_system_prompt_md(content: str = Form(...)) -> Any:
        try:
            write_system_prompt_raw(content)
        except SystemPromptError as e:
            return HTMLResponse(
                f'<p class="st-error">Ошибка: {html.escape(str(e))}</p>',
                status_code=400,
            )
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/system_prompt.md</p>'
        )

    @router.post("/api/prompts/global-policy-md", response_class=HTMLResponse)
    async def api_save_global_policy_md(content: str = Form("")) -> Any:
        write_global_model_policy_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/global_model_policy.md</p>'
        )

    @router.post("/api/prompts/dream-decomposition-md", response_class=HTMLResponse)
    async def api_save_dream_decomposition_md(content: str = Form("")) -> Any:
        write_dream_decomposition_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/dream_decomposition.md (Сценарист 0B)</p>'
        )

    @router.post("/api/prompts/dream-beat-planner-md", response_class=HTMLResponse)
    async def api_save_dream_beat_planner_md(content: str = Form("")) -> Any:
        write_dream_beat_planner_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/dream_beat_planner.md (Beat Planner 0A)</p>'
        )

    @router.post("/api/prompts/dream-scene-motion-decompose-md", response_class=HTMLResponse)
    async def api_save_dream_scene_motion_decompose_md(content: str = Form("")) -> Any:
        write_dream_scene_motion_decompose_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/dream_scene_motion_decompose.md (pipeline: сцены+motion)</p>'
        )

    @router.post("/api/prompts/dream-image-prompts-md", response_class=HTMLResponse)
    async def api_save_dream_image_prompts_md(content: str = Form("")) -> Any:
        write_dream_image_prompts_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/dream_image_prompts.md</p>'
        )

    @router.post("/api/prompts/dream-intent-routing-md", response_class=HTMLResponse)
    async def api_save_dream_intent_routing_md(content: str = Form("")) -> Any:
        write_dream_intent_routing_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/dream_intent_routing.md</p>'
        )

    @router.post("/api/prompts/dream-director-references-md", response_class=HTMLResponse)
    async def api_save_dream_director_references_md(content: str = Form("")) -> Any:
        write_dream_director_references_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/dream_director_references.md (Режиссёр 1A)</p>'
        )

    @router.post("/api/prompts/dream-director-keyframes-md", response_class=HTMLResponse)
    async def api_save_dream_director_keyframes_md(content: str = Form("")) -> Any:
        write_dream_director_keyframes_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: prompts/dream_director_keyframes.md (Режиссёр 1B)</p>'
        )

    @router.post("/api/contracts/dream-director-references-user-md", response_class=HTMLResponse)
    async def api_save_dream_director_references_user_contract(content: str = Form("")) -> Any:
        write_dream_director_references_user_contract_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: contracts/dream_director_references_user.md (user-контракт 1A)</p>'
        )

    @router.post("/api/contracts/dream-director-keyframes-user-md", response_class=HTMLResponse)
    async def api_save_dream_director_keyframes_user_contract(content: str = Form("")) -> Any:
        write_dream_director_keyframes_user_contract_raw(content)
        return HTMLResponse(
            '<p class="muted" style="color:#56d364">Сохранено: contracts/dream_director_keyframes_user.md (user-контракт 1B)</p>'
        )

    @router.get("/partials/tools/execution", response_class=HTMLResponse)
    async def partial_tools_execution_detail(
        request: Request,
        exec_id: str = Query(...),
    ) -> Any:
        detail = get_execution_detail(
            exec_id=unquote(exec_id).strip(),
            chat_store=chat_store,
            video_job_repo=video_job_repo,
        )
        timeline: list[dict[str, Any]] = []
        if detail and detail.get("trace_id"):
            timeline = trace_timeline(
                str(detail["trace_id"]),
                obs_repo,
                limit=150,
            )[-40:]
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/tools_execution_detail.html",
            {"detail": detail, "timeline": timeline, "exec_id": exec_id},
        )

    @router.post("/api/tools/registry", response_class=HTMLResponse)
    async def api_tools_registry_save(
        request: Request,
        tool_name: str = Form(...),
        enabled: str | None = Form(default=None),
        description: str = Form(""),
        timeout_sec: str = Form(""),
        retry_count: str = Form(""),
        polling_interval_sec: str = Form(""),
        hint: str = Form(""),
    ) -> Any:
        overrides = load_tool_overrides(settings.data_dir)
        entry = dict(overrides.get(tool_name) or {})
        entry["enabled"] = bool(enabled)
        entry["description"] = (description or "").strip()
        if (timeout_sec or "").strip().isdigit():
            entry["timeout_sec"] = int(timeout_sec)
        else:
            entry.pop("timeout_sec", None)
        if (retry_count or "").strip().isdigit():
            entry["retry_count"] = int(retry_count)
        else:
            entry.pop("retry_count", None)
        if (polling_interval_sec or "").strip().replace(".", "", 1).isdigit():
            entry["polling_interval_sec"] = float(polling_interval_sec)
        else:
            entry.pop("polling_interval_sec", None)
        entry["hint"] = (hint or "").strip()
        overrides[tool_name] = entry
        save_tool_overrides(settings.data_dir, overrides)
        ctx = _tools_frame_ctx(period="month")
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/tools_frame_agent_control.html",
            _tools_frame_with_model_picker(settings, ctx),
        )

    @router.post("/api/tools/policies", response_class=HTMLResponse)
    async def api_tools_policies_save(
        request: Request,
        available_tools_note: str = Form(""),
        usage_rules: str = Form(""),
        fallback_logic: str = Form(""),
        default_language: str = Form("ru"),
        call_conditions: str = Form(""),
    ) -> Any:
        extra = load_policies_extra(settings.data_dir)
        extra.update(
            {
                "available_tools_note": available_tools_note,
                "usage_rules": usage_rules,
                "fallback_logic": fallback_logic,
                "default_language": (default_language or "ru").strip() or "ru",
                "call_conditions": call_conditions,
            }
        )
        save_policies_extra(settings.data_dir, extra)
        ctx = _tools_frame_ctx(period="month")
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/tools_frame_agent_control.html",
            _tools_frame_with_model_picker(settings, ctx),
        )

    @router.post("/api/tools/active-set", response_class=HTMLResponse)
    async def api_tools_active_set(
        request: Request,
        period: str = Form("month"),
        custom_start: str = Form(""),
        custom_end: str = Form(""),
    ) -> Any:
        form = await request.form()
        selected = {
            str(v)
            for v in form.getlist("selected_tools")
            if str(v).strip()
        }
        rows = _tools_frame_ctx(
            period=(period or "month").strip() or "month",
            custom_start=(custom_start or "").strip() or None,
            custom_end=(custom_end or "").strip() or None,
        )["registry_rows"]
        overrides = load_tool_overrides(settings.data_dir)
        for row in rows:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            entry = dict(overrides.get(name) or {})
            entry["enabled"] = name in selected
            overrides[name] = entry
        save_tool_overrides(settings.data_dir, overrides)
        ctx = _tools_frame_ctx(
            period=(period or "month").strip() or "month",
            custom_start=(custom_start or "").strip() or None,
            custom_end=(custom_end or "").strip() or None,
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/tools_frame_agent_control.html",
            _tools_frame_with_model_picker(settings, ctx),
        )

    @router.get(
        "/partials/messages/{message_id}/detail",
        response_class=HTMLResponse,
    )
    async def partial_message_detail(
        request: Request,
        message_id: str,
    ) -> Any:
        detail = get_message_detail(
            message_id, message_repo, obs_repo, chat_store=chat_store
        )
        if not detail:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/message_detail.html",
                {"error": "Сообщение не найдено", "detail": None},
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/message_detail.html",
            {"error": None, "detail": detail},
        )

    @router.post("/api/generate", response_class=HTMLResponse)
    async def api_generate(
        request: Request,
        prompt: str = Form(...),
        size: str = Form("1024*1536"),
        model: str = Form("qwen-image-2.0"),
        n: int = Form(1),
        dream_asset_id: str | None = Form(None),
    ) -> Any:
        prompt_clean = (prompt or "").strip()
        if not prompt_clean:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/generate_result.html",
                {
                    "error": "Пустой prompt",
                    "ok": False,
                    "urls": [],
                    "prompt": "",
                    "seconds": 0.0,
                    "model": model,
                    "size": size,
                },
            )
        n = max(1, min(6, int(n)))
        aid = (dream_asset_id or "").strip()
        ref: str | None = None
        if aid:
            asset = dream_asset_repo.find_by_id_sync(aid)
            if not asset:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/generate_result.html",
                    {
                        "error": f"Ассет не найден: {aid}",
                        "ok": False,
                        "urls": [],
                        "prompt": prompt_clean,
                        "seconds": 0.0,
                        "model": model,
                        "size": size,
                    },
                )
            ref = resolve_dream_asset_image_ref_for_qwen(
                asset,
                bot_token=(settings.telegram_bot_token or ""),
            )
            if not ref:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/generate_result.html",
                    {
                        "error": "Не удалось получить картинку для референса (нужен source_image_url или TELEGRAM_BOT_TOKEN + telegram_file_id).",
                        "ok": False,
                        "urls": [],
                        "prompt": prompt_clean,
                        "seconds": 0.0,
                        "model": model,
                        "size": size,
                    },
                )
        t0 = time.perf_counter()
        if ref:
            result = tool_edit_image(
                image_source=ref,
                instruction=prompt_clean,
                size=size,
                model=model,
                n=n,
            )
        else:
            result = tool_generate_image(
                prompt=prompt_clean,
                size=size,
                model=model,
                n=n,
            )
        elapsed = time.perf_counter() - t0
        try:
            record_dev_usage(
                dev_usage_ledger_repo,
                category="image",
                provider="dashscope",
                model=model,
                source="dev.api.generate",
                meta={
                    "n": n,
                    "size": size,
                    "seconds": round(elapsed, 3),
                    "dream_asset_id": aid or None,
                    "mode": "edit" if ref else "generate",
                },
                ok=result.ok,
            )
        except Exception:  # noqa: BLE001
            pass
        if not result.ok:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/generate_result.html",
                {
                    "error": result.error or "Unknown error",
                    "ok": False,
                    "urls": [],
                    "prompt": prompt_clean,
                    "seconds": elapsed,
                    "model": model,
                    "size": size,
                },
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/generate_result.html",
            {
                "error": None,
                "ok": True,
                "urls": result.image_urls,
                "prompt": prompt_clean,
                "seconds": elapsed,
                "model": model,
                "size": size,
            },
        )

    @router.post("/api/generate/openrouter", response_class=HTMLResponse)
    async def api_generate_openrouter(
        request: Request,
        prompt: str = Form(...),
        model: str = Form(""),
        aspect_ratio: str = Form(""),
        image_size: str = Form(""),
        dream_asset_id: str | None = Form(None),
    ) -> Any:
        prompt_clean = (prompt or "").strip()
        if not prompt_clean:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/generate_result.html",
                {
                    "error": "Пустой prompt",
                    "ok": False,
                    "urls": [],
                    "prompt": "",
                    "seconds": 0.0,
                    "model": (model or "").strip() or settings.openrouter_image_model,
                    "size": "",
                },
            )
        aid = (dream_asset_id or "").strip()
        ref_urls: list[str] = []
        if aid:
            asset = dream_asset_repo.find_by_id_sync(aid)
            if not asset:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/generate_result.html",
                    {
                        "error": f"Ассет не найден: {aid}",
                        "ok": False,
                        "urls": [],
                        "prompt": prompt_clean,
                        "seconds": 0.0,
                        "model": (model or "").strip() or settings.openrouter_image_model,
                        "size": "",
                    },
                )
            r = resolve_dream_asset_image_ref_for_qwen(
                asset,
                bot_token=(settings.telegram_bot_token or ""),
            )
            if not r:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/generate_result.html",
                    {
                        "error": "Не удалось получить картинку для референса (нужен source_image_url или TELEGRAM_BOT_TOKEN + telegram_file_id).",
                        "ok": False,
                        "urls": [],
                        "prompt": prompt_clean,
                        "seconds": 0.0,
                        "model": (model or "").strip() or settings.openrouter_image_model,
                        "size": "",
                    },
                )
            ref_urls = [r]
        m = (model or "").strip() or None
        ar = (aspect_ratio or "").strip() or None
        iz = (image_size or "").strip() or None
        size_label = f"{ar or '—'} · {iz or '—'}"
        model_label = m or (settings.openrouter_image_model or "openrouter")
        t0 = time.perf_counter()
        result = tool_generate_image_openrouter(
            prompt_clean,
            aspect_ratio=ar,
            image_size=iz,
            model=m,
            reference_image_urls=ref_urls if ref_urls else None,
        )
        elapsed = time.perf_counter() - t0
        try:
            inp, outp, tot, cost = normalize_openrouter_usage(
                result.usage if isinstance(result.usage, dict) else None
            )
            record_dev_usage(
                dev_usage_ledger_repo,
                category="image_openrouter",
                provider="openrouter",
                model=model_label,
                source="dev.api.generate.openrouter",
                input_tokens=inp,
                output_tokens=outp,
                total_tokens=tot,
                cost_usd=cost,
                meta={
                    "seconds": round(elapsed, 3),
                    "dream_asset_id": aid or None,
                    "has_ref": bool(ref_urls),
                },
                ok=result.ok,
            )
        except Exception:  # noqa: BLE001
            pass
        if not result.ok:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/generate_result.html",
                {
                    "error": result.error or "Unknown error",
                    "ok": False,
                    "urls": [],
                    "prompt": prompt_clean,
                    "seconds": elapsed,
                    "model": model_label,
                    "size": size_label,
                },
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/generate_result.html",
            {
                "error": None,
                "ok": True,
                "urls": result.image_urls,
                "prompt": prompt_clean,
                "seconds": elapsed,
                "model": model_label,
                "size": size_label,
            },
        )

    @router.get("/partials/dream_assets/users", response_class=HTMLResponse)
    async def partial_dream_users(request: Request) -> Any:
        uids = dream_asset_repo.list_distinct_owner_ids_sync()
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_users.html",
            {"user_ids": uids},
        )

    @router.get("/partials/dream_assets/for_user", response_class=HTMLResponse)
    async def partial_dream_for_user(
        request: Request,
        uid: int = Query(..., description="telegram / owner user id"),
    ) -> Any:
        assets = dream_asset_repo.list_by_owner_sync(uid)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_assets_table.html",
            {"user_id": uid, "assets": assets},
        )

    @router.get("/partials/playground/user_buttons", response_class=HTMLResponse)
    async def partial_playground_user_buttons(
        request: Request,
        slot: str = Query("qwen"),
    ) -> Any:
        key = (slot or "qwen").strip().lower()
        tpl = _PG_USER_BUTTON_SLOTS.get(key) or _PG_USER_BUTTON_SLOTS["qwen"]
        host_id, form_id = tpl
        uids = dream_asset_repo.list_distinct_owner_ids_sync()
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/playground_user_buttons.html",
            {
                "user_ids": uids,
                "asset_host_id": host_id,
                "form_id": form_id,
            },
        )

    @router.get("/partials/playground/user_assets", response_class=HTMLResponse)
    async def partial_playground_user_assets(
        request: Request,
        uid: int = Query(..., description="owner user id"),
        form_id: str = Query(...),
    ) -> Any:
        fid = (form_id or "").strip()
        if fid not in _PLAYGROUND_FORM_IDS:
            fid = "form-playground-qwen"
        assets = dream_asset_repo.list_by_owner_sync(uid)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/playground_user_assets.html",
            {
                "user_id": uid,
                "form_id": fid,
                "assets": assets,
            },
        )

    @router.get("/partials/playground/lib_user_list", response_class=HTMLResponse)
    async def partial_playground_lib_user_list(request: Request) -> Any:
        uids = dream_asset_repo.list_distinct_owner_ids_sync()
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/playground_lib_user_list.html",
            {"user_ids": uids},
        )

    @router.post("/api/video/upload", response_class=HTMLResponse)
    async def dev_video_upload(
        request: Request,
        file: UploadFile = File(...),
        upload_slot: str = Form("first"),
    ) -> Any:
        slot = (upload_slot or "first").strip().lower()
        if slot not in ("first", "last"):
            slot = "first"
        udir = _upload_dir(settings)
        udir.mkdir(parents=True, exist_ok=True)
        raw = await file.read()
        if len(raw) > 10 * 1024 * 1024:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/video_upload_result.html",
                {
                    "error": "Файл больше 10 MB",
                    "upload_id": None,
                    "filename": None,
                    "slot": slot,
                },
            )
        orig = file.filename or "image"
        ext = Path(orig).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
            ext = ".jpg"
        fname = f"{uuid.uuid4().hex}{ext}"
        path = udir / fname
        path.write_bytes(raw)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_upload_result.html",
            {"error": None, "upload_id": fname, "filename": orig, "slot": slot},
        )

    @router.post("/api/video/jobs", response_class=HTMLResponse)
    async def dev_video_create_job(
        request: Request,
        source_mode: str = Form(...),
        prompt: str = Form(...),
        video_backend: str = Form("dashscope"),
        model: str = Form("wan2.7-i2v"),
        openrouter_model: str | None = Form(None),
        openrouter_provider_json: str | None = Form(None),
        duration: int = Form(4),
        resolution: str = Form("720p"),
        dream_asset_id: str | None = Form(None),
        owner_user_id: str | None = Form(None),
        upload_id: str | None = Form(None),
        last_frame_upload_id: str | None = Form(None),
    ) -> Any:
        prompt_clean = (prompt or "").strip()
        if not prompt_clean:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/video_error.html",
                {"message": "Пустой prompt"},
            )
        dur = max(2, min(15, int(duration)))
        backend = (video_backend or "dashscope").strip().lower()
        if backend not in ("dashscope", "openrouter"):
            backend = "dashscope"

        or_provider: dict[str, Any] | None = None
        raw_prov = (openrouter_provider_json or "").strip()
        if raw_prov:
            try:
                parsed = json.loads(raw_prov)
                if not isinstance(parsed, dict):
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {"message": "openrouter_provider_json должен быть JSON-объектом {...}"},
                    )
                or_provider = parsed
            except json.JSONDecodeError:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/video_error.html",
                    {"message": "Невалидный JSON в поле provider (OpenRouter)."},
                )
        last_uri: str | None = None
        lf_id = (last_frame_upload_id or "").strip()
        if lf_id:
            if not _UPLOAD_ID_RE.match(lf_id):
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/video_error.html",
                    {"message": "Некорректный last_frame_upload_id (ожидается upload_id из dev upload)."},
                )
            lf_path = _upload_dir(settings) / lf_id
            if not lf_path.is_file():
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/video_error.html",
                    {"message": f"Файл конечного кадра не найден: {lf_id}"},
                )
            try:
                last_uri, _lf_meta = load_local_file_as_data_uri(lf_path)
            except AssetSourceError as e:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/video_error.html",
                    {"message": str(e)},
                )
        try:
            if source_mode.strip() == "dream_asset":
                if not dream_asset_id:
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {
                            "message": "Выберите dream asset (радиокнопка) или переключите режим на загрузку файла.",
                        },
                    )
                asset = dream_asset_repo.find_by_id_sync(dream_asset_id)
                if not asset:
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {"message": "Asset не найден в MongoDB."},
                    )
                uri, meta = dream_asset_to_data_uri(
                    asset,
                    bot_token=settings.telegram_bot_token,
                )
                owner = str(asset.get("owner_user_id") or owner_user_id or "dev")
            elif source_mode.strip() == "upload":
                if not upload_id or not _UPLOAD_ID_RE.match(upload_id):
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {
                            "message": "Сначала загрузите файл (кнопка «Загрузить») или выберите dream asset.",
                        },
                    )
                path = _upload_dir(settings) / upload_id
                if not path.is_file():
                    return _TEMPLATES.TemplateResponse(
                        request,
                        "partials/video_error.html",
                        {"message": f"Файл загрузки не найден: {upload_id}"},
                    )
                uri, meta = load_local_file_as_data_uri(path)
                owner = (owner_user_id or "").strip() or "dev_upload"
            else:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/video_error.html",
                    {"message": f"Неизвестный source_mode: {source_mode}"},
                )
        except AssetSourceError as e:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/video_error.html",
                {"message": str(e)},
            )

        job_extra = {**meta, "dev_ui": True}
        if last_uri:
            job_extra["last_frame_dev_upload_id"] = lf_id
        result = tool_image_to_video(
            prompt=prompt_clean,
            image_url=uri,
            duration=dur,
            resolution=resolution,
            owner_user_id=owner,
            model=model,
            last_frame_url=last_uri,
            job_extra=job_extra,
            video_backend=backend,
            openrouter_model=(openrouter_model or "").strip() or None,
            openrouter_provider=or_provider,
        )
        job_id = result.get("job_id")
        if not job_id:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/video_error.html",
                {
                    "message": result.get("error") or "Не удалось создать job",
                },
            )
        job = video_job_repo.get_job_sync(job_id)
        try:
            usage_model = (
                (openrouter_model or "").strip() or settings.openrouter_video_model
                if backend == "openrouter"
                else model
            )
            record_dev_usage(
                dev_usage_ledger_repo,
                category="video",
                provider="openrouter" if backend == "openrouter" else "wan",
                model=usage_model,
                source="dev.api.video.jobs",
                meta={
                    "job_id": job_id,
                    "source_mode": source_mode.strip(),
                    "video_backend": backend,
                    "duration": dur,
                    "resolution": resolution,
                },
                ok=True,
            )
        except Exception:  # noqa: BLE001
            pass
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_job_tracker.html",
            {"job": job},
        )

    @router.get("/partials/video/users", response_class=HTMLResponse)
    async def partial_video_users(request: Request) -> Any:
        uids = dream_asset_repo.list_distinct_owner_ids_sync()
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_users.html",
            {"user_ids": uids},
        )

    @router.get("/partials/video/asset_picker", response_class=HTMLResponse)
    async def partial_video_asset_picker(
        request: Request,
        uid: int = Query(..., description="owner user id"),
    ) -> Any:
        assets = dream_asset_repo.list_by_owner_sync(uid, limit=120)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_asset_picker.html",
            {"uid": uid, "assets": assets, "error": None},
        )

    @router.get("/partials/video/job_tracker", response_class=HTMLResponse)
    async def partial_video_job_tracker(
        request: Request,
        job_id: str = Query(...),
    ) -> Any:
        job = video_job_repo.get_job_sync(job_id)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_job_tracker.html",
            {"job": job},
        )

    @router.get("/partials/video/jobs_rows", response_class=HTMLResponse)
    async def partial_video_jobs_rows(request: Request) -> Any:
        jobs = video_job_repo.list_recent_sync(limit=50)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_jobs_rows.html",
            {"jobs": jobs},
        )

    @router.get("/partials/video/job_detail", response_class=HTMLResponse)
    async def partial_video_job_detail(
        request: Request,
        job_id: str = Query(...),
    ) -> Any:
        job = video_job_repo.get_job_sync(job_id)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/video_job_detail.html",
            {"job": job},
        )

    @router.get("/partials/dream/stage1_prompt_lab", response_class=HTMLResponse)
    async def partial_dream_stage1_prompt_lab(request: Request) -> Any:
        from services.observability.dream_stage1_lab import build_dream_stage1_lab_context

        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_stage1_prompt_lab.html",
            build_dream_stage1_lab_context(),
        )

    @router.get("/partials/dream/pipeline_lite_tab", response_class=HTMLResponse)
    async def partial_dream_pipeline_lite_tab(request: Request) -> Any:
        s = get_settings()
        catalog = _dream_lite_catalog_with_test_stats()
        video_catalog = _dream_lite_video_catalog_with_stats()
        active_profile = dream_lite_run_repo.get_active_profile_sync() if dream_lite_run_repo else None
        active_rc = (
            (active_profile or {}).get("run_config")
            if isinstance((active_profile or {}).get("run_config"), dict)
            else {}
        )
        active_image_policy = (
            active_rc.get("image_policy")
            if isinstance(active_rc.get("image_policy"), dict)
            else {}
        )
        profile_selected_mid = str(active_image_policy.get("model") or "").strip()
        profile_simple_mode = bool(active_image_policy.get("simple_mode"))
        selected_mid = profile_selected_mid or (s.openrouter_image_model or "").strip()
        if profile_simple_mode and not selected_mid:
            selected_mid = _SIMPLE_MODE_RECOMMENDED_IMAGE_MODEL
        if not selected_mid and catalog:
            selected_mid = str((catalog[0] or {}).get("id") or "").strip()
        active_video = _active_lite_video_policy()
        selected_video_model = str(active_video.get("openrouter_model") or "").strip() or str(active_video.get("i2v_model") or "").strip()
        selected_prompt_mode = str(active_video.get("prompt_mode") or "first_last_frame").strip() or "first_last_frame"
        selected_montage_preset = str(active_video.get("montage_preset") or "default").strip() or "default"
        selected_audio_required = bool(active_video.get("audio_required"))
        if not selected_video_model and video_catalog:
            selected_video_model = str((video_catalog[0] or {}).get("model_id") or "").strip()
        draft_profile = dream_lite_run_repo.get_profile_sync(profile_name="default", status="Draft") if dream_lite_run_repo else None
        latest_lite_run_id = ""
        if dream_lite_run_repo is not None:
            recent = dream_lite_run_repo.list_recent_runs_sync(limit=1, user_id=int(s.dream_lite_playground_user_id))
            if recent:
                latest_lite_run_id = str((recent[0] or {}).get("lite_run_id") or "")
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_tab.html",
            {
                "dream_pipeline_lite_env_prompt": read_dream_pipeline_lite_environments_raw(),
                "dream_pipeline_lite_env_simple_prompt": read_dream_pipeline_lite_environments_simple_raw(),
                "dream_pipeline_lite_frames_prompt": read_dream_pipeline_lite_frames_raw(),
                "dream_pipeline_lite_frames_prev_link_prompt": read_dream_pipeline_lite_frames_prev_link_raw(),
                "dream_pipeline_lite_transitions_prompt": read_dream_pipeline_lite_transitions_raw(),
                "dream_pipeline_lite_transitions_seedance_prompt": read_dream_pipeline_lite_transitions_seedance_raw(),
                "dream_pipeline_lite_transitions_wan26_prompt": read_dream_pipeline_lite_transitions_wan26_raw(),
                "dream_pipeline_lite_transitions_kling_ref_prompt": read_dream_pipeline_lite_transitions_kling_ref_raw(),
                "image_models_catalog": catalog,
                "selected_image_model": selected_mid,
                "simple_mode": profile_simple_mode,
                "simple_mode_recommended_model": _SIMPLE_MODE_RECOMMENDED_IMAGE_MODEL,
                "selected_model_insight": _model_insight_from_catalog(catalog, selected_mid, last_n=5),
                "video_models_catalog": video_catalog,
                "selected_video_model": selected_video_model,
                "selected_prompt_mode": selected_prompt_mode,
                "selected_montage_preset": selected_montage_preset,
                "selected_audio_required": selected_audio_required,
                "selected_video_model_insight": _video_model_insight_from_catalog(video_catalog, selected_video_model, last_n=5),
                "openrouter_video_models_catalog": openrouter_video_models_catalog(),
                "active_video_policy": active_video,
                "model_registry": model_capability_registry(),
                "active_profile_meta": active_profile or {},
                "draft_profile_meta": draft_profile or {},
                "dream_lite_playground_user_id": int(s.dream_lite_playground_user_id),
                "latest_lite_run_id": latest_lite_run_id,
            },
        )

    @router.post("/api/dream/lite/model_insight_card", response_class=HTMLResponse)
    async def api_dream_lite_model_insight_card(model_id: str = Form("")) -> Any:
        catalog = _dream_lite_catalog_with_test_stats()
        mid = (model_id or "").strip()
        if not mid and catalog:
            mid = str((catalog[0] or {}).get("id") or "").strip()
        insight = _model_insight_from_catalog(catalog, mid, last_n=5)

        def _fmt(v: Any) -> str:
            if v is None or v == "":
                return "—"
            return str(v)

        status = str(insight.get("quality_status") or "no_data_yet")
        refs_lvl = str(insight.get("refs_quality_level") or "no_data_yet")
        status_cls = "ok" if status == "tested" else "muted"
        refs_cls = "ok" if refs_lvl == "good" else ("warn" if refs_lvl == "limited" else "err" if refs_lvl == "degraded" else "muted")
        usage_text = (
            "usage_unavailable"
            if bool(insight.get("usage_unavailable"))
            else f"in={_fmt(insight.get('avg_tokens_in_last_n'))}, out={_fmt(insight.get('avg_tokens_out_last_n'))}, total={_fmt(insight.get('avg_total_tokens_last_n'))}"
        )
        body = (
            '<article class="pipe-stage-card dream-lite-input-card dream-lite-debug-inner">'
            '<h5 class="dream-lite-secondary">Model insight</h5>'
            f'<p class="dream-lite-secondary">status: <span class="dream-lite-pill dream-lite-pill--{status_cls}">{html.escape(status)}</span> '
            f'· tested_status: <code>{html.escape(str(insight.get("tested_status") or "untested"))}</code> '
            f'· runs: <code>{int(insight.get("runs_count") or 0)}</code></p>'
            f'<p class="dream-lite-secondary"><strong>Timing:</strong> avg_duration_ms(last5)=<code>{_fmt(insight.get("avg_duration_ms_last_n"))}</code>, '
            f'avg_provider_latency_ms(last5)=<code>{_fmt(insight.get("avg_provider_latency_ms_last_n"))}</code>, samples=<code>{int(insight.get("samples_count") or 0)}</code></p>'
            f'<p class="dream-lite-secondary"><strong>Tokens:</strong> <code>{html.escape(usage_text)}</code></p>'
            f'<p class="dream-lite-secondary"><strong>Refs quality:</strong> <span class="dream-lite-pill dream-lite-pill--{refs_cls}">{html.escape(refs_lvl)}</span> '
            f'{html.escape(str(insight.get("refs_quality_note") or "Not tested yet"))}</p>'
            "</article>"
        )
        return HTMLResponse(body)

    @router.post("/api/dream/lite/video_model_insight_card", response_class=HTMLResponse)
    async def api_dream_lite_video_model_insight_card(model_id: str = Form("")) -> Any:
        catalog = _dream_lite_video_catalog_with_stats()
        mid = (model_id or "").strip()
        if not mid and catalog:
            mid = str((catalog[0] or {}).get("model_id") or "").strip()
        insight = _video_model_insight_from_catalog(catalog, mid, last_n=5)

        def _fmt(v: Any) -> str:
            if v is None or v == "":
                return "—"
            return str(v)

        status = str(insight.get("quality_status") or "no_data_yet")
        refs_lvl = str(insight.get("refs_quality_level") or "no_data_yet")
        status_cls = "ok" if status == "tested" else "muted"
        refs_cls = "ok" if refs_lvl == "good" else ("warn" if refs_lvl == "limited" else ("err" if refs_lvl == "degraded" else "muted"))
        usage_text = (
            "usage_unavailable"
            if bool(insight.get("usage_unavailable"))
            else f"in={_fmt(insight.get('avg_tokens_in_last_n'))}, out={_fmt(insight.get('avg_tokens_out_last_n'))}, total={_fmt(insight.get('avg_total_tokens_last_n'))}"
        )
        body = (
            '<article class="pipe-stage-card dream-lite-input-card dream-lite-debug-inner">'
            '<h5 class="dream-lite-secondary">Video model insight</h5>'
            f'<p class="dream-lite-secondary">status: <span class="dream-lite-pill dream-lite-pill--{status_cls}">{html.escape(status)}</span> '
            f'· tested_status: <code>{html.escape(str(insight.get("tested_status") or "untested"))}</code> '
            f'· runs: <code>{int(insight.get("runs_count") or 0)}</code></p>'
            f'<p class="dream-lite-secondary"><strong>Timing:</strong> avg_duration_ms(last5)=<code>{_fmt(insight.get("avg_duration_ms_last_n"))}</code>, '
            f'avg_provider_latency_ms(last5)=<code>{_fmt(insight.get("avg_provider_latency_ms_last_n"))}</code>, samples=<code>{int(insight.get("samples_count") or 0)}</code></p>'
            f'<p class="dream-lite-secondary"><strong>Tokens:</strong> <code>{html.escape(usage_text)}</code></p>'
            f'<p class="dream-lite-secondary"><strong>Refs quality:</strong> <span class="dream-lite-pill dream-lite-pill--{refs_cls}">{html.escape(refs_lvl)}</span> '
            f'{html.escape(str(insight.get("refs_quality_note") or "Not tested yet"))}</p>'
            "</article>"
        )
        return HTMLResponse(body)

    @router.post("/api/dream/lite/video_contract_preview", response_class=HTMLResponse)
    async def api_dream_lite_video_contract_preview(
        model_id: str = Form(""),
        image_url: str = Form(""),
        last_frame_url: str = Form(""),
        motion_prompt: str = Form(""),
        prompt_mode: str = Form("first_last_frame"),
        audio_required: str = Form(""),
        duration: str = Form("4"),
        resolution: str = Form("720p"),
    ) -> Any:
        active_video = _active_lite_video_policy()
        locked = _is_seedance_audio_locked(active_video) or _is_kling_reference_preset(active_video)
        mid = (model_id or "").strip()
        if locked:
            mid = (
                str(active_video.get("openrouter_model") or "").strip()
                or str(active_video.get("i2v_model") or "").strip()
                or mid
            )
        prof = get_video_model_profile(mid)
        if not prof:
            return HTMLResponse('<p class="dream-lite-secondary">Профиль видео-модели не найден.</p>', status_code=404)
        audio_req = str(audio_required or "").strip().lower() in {"1", "true", "on", "yes"}
        requested_pm = (prompt_mode or "first_last_frame").strip() or "first_last_frame"
        if locked:
            requested_pm = str(active_video.get("prompt_mode") or requested_pm).strip() or requested_pm
            audio_req = True
        pm, effective_policy, locked_effective = _effective_video_prompt_policy(
            prompt_mode=requested_pm,
            montage_preset=str(active_video.get("montage_preset") or "default"),
            audio_required=audio_req,
        )
        ok_mm, reason_mm = _validate_video_mode_model(pm, mid, audio_required=audio_req)
        if not ok_mm:
            return HTMLResponse(
                f'<p class="dream-lite-secondary">Несовместимая связка mode+model: <code>{html.escape(pm)}</code> + <code>{html.escape(mid)}</code> ({html.escape(reason_mm)}).</p>',
                status_code=400,
            )
        try:
            dur = max(1, int((duration or "4").strip() or "4"))
        except Exception:
            dur = 4
        prompt = (motion_prompt or "").strip() or "Cinematic motion between storyboard keyframes."
        ff = (image_url or "").strip()
        lf = (last_frame_url or "").strip() if pm == "first_last_frame" else ""
        internal_payload = {
            "task_type": "image_to_video",
            "prompt_mode": pm,
            "prompt": prompt,
            "first_frame": ff,
            "last_frame": lf,
            "duration": dur,
            "resolution": (resolution or "720p").strip() or "720p",
            "scene_id": "preview_scene",
            "transition_id": "preview_transition",
            "camera_motion": prompt,
        }
        preview = build_provider_request_from_internal_video_payload(
            internal_payload=internal_payload,
            model_profile=prof,
        )
        status = str(preview.get("status") or "blocked")
        status_cls = "ok" if status == "full" else ("warn" if status == "degraded" else "err")
        pr_id = "dream-lite-video-provider-json"

        def _pre(obj: Any) -> str:
            return html.escape(json.dumps(obj, ensure_ascii=False, indent=2))

        blocks: list[str] = [
            '<article class="pipe-stage-card dream-lite-input-card dream-lite-debug-inner dream-lite-frame-contract">',
            f'<p class="dream-lite-secondary">Audit status: <span class="dream-lite-pill dream-lite-pill--{status_cls}">{html.escape(status)}</span></p>',
            f'<p class="dream-lite-secondary"><strong>Prompt mode:</strong> <code>{html.escape(str(preview.get("prompt_mode") or internal_payload.get("prompt_mode") or "first_last_frame"))}</code></p>',
            f'<p class="dream-lite-secondary"><strong>Effective policy:</strong> <code>{html.escape(effective_policy)}</code> · locked=<code>{str(bool(locked_effective)).lower()}</code></p>',
            '<h5 class="dream-lite-secondary">Video Model Contract</h5>',
            f'<pre class="dream-lite-textarea dream-lite-textarea--mono" style="max-height:220px;overflow:auto">{_pre(prof)}</pre>',
            '<h5 class="dream-lite-secondary">Video Adapter Result</h5>',
            f'<pre class="dream-lite-textarea dream-lite-textarea--mono" style="max-height:180px;overflow:auto">{_pre({"accepted_fields": preview.get("accepted_fields"), "dropped_fields": preview.get("dropped_fields"), "warnings": preview.get("warnings"), "errors": preview.get("errors")})}</pre>',
            '<h5 class="dream-lite-secondary">Final Provider JSON</h5>',
            f'<textarea id="{pr_id}" class="dream-lite-textarea dream-lite-textarea--mono" style="min-height:180px">{html.escape(json.dumps(preview.get("provider_request") or {}, ensure_ascii=False, indent=2))}</textarea>',
            '<div class="dream-lite-actions">'
            f"<button type=\"button\" class=\"btn-ghost\" onclick=\"navigator.clipboard.writeText(document.getElementById('{pr_id}').value)\">Copy Provider JSON</button>"
            "</div>",
            "</article>",
        ]
        return HTMLResponse("".join(blocks))

    @router.post("/api/dream/lite/config/apply_video_model", response_class=HTMLResponse)
    async def api_dream_lite_apply_video_model(
        model_id: str = Form(""),
        prompt_mode: str = Form("first_last_frame"),
        audio_required: str = Form(""),
        duration: str = Form("4"),
        resolution: str = Form("720p"),
    ) -> Any:
        active_video = _active_lite_video_policy()
        locked = _is_seedance_audio_locked(active_video) or _is_kling_reference_preset(active_video)
        mid = (model_id or "").strip()
        if locked:
            mid = (
                str(active_video.get("openrouter_model") or "").strip()
                or str(active_video.get("i2v_model") or "").strip()
                or mid
            )
        prof = get_video_model_profile(mid)
        if not prof:
            return HTMLResponse('<p class="dream-lite-secondary">Выберите корректную видео-модель.</p>', status_code=400)
        pm = (prompt_mode or "first_last_frame").strip() or "first_last_frame"
        audio_req = str(audio_required or "").strip().lower() in {"1", "true", "on", "yes"}
        if locked:
            pm = str(active_video.get("prompt_mode") or pm).strip() or pm
            if _is_seedance_audio_locked(active_video):
                audio_req = True
        backend = str(prof.get("backend") or prof.get("provider") or "").strip()
        i2v_model = "wan2.7-i2v"
        openrouter_model = ""
        if backend == "openrouter":
            openrouter_model = mid
        else:
            i2v_model = mid
        montage_preset = lite_resolve_montage_preset(
            selected_video_model=mid,
            configured_preset="",
        )
        pm, effective_policy, locked_effective = _effective_video_prompt_policy(
            prompt_mode=pm,
            montage_preset=montage_preset,
            audio_required=audio_req,
        )
        ok_mm, reason_mm = _validate_video_mode_model(pm, mid, audio_required=audio_req)
        if not ok_mm:
            return HTMLResponse(
                f'<p class="dream-lite-secondary">Нельзя применить связку <code>{html.escape(pm)}</code> + <code>{html.escape(mid)}</code>: {html.escape(reason_mm)}.</p>',
                status_code=400,
            )
        bundle_vp = video_policy_bundle_for_montage_preset(montage_preset)
        try:
            dur = max(1, int((duration or "4").strip() or "4"))
        except Exception:
            dur = 4
        res_eff = (resolution or "720p").strip() or "720p"
        if montage_preset == "seedance":
            dur = int(bundle_vp.get("duration_sec") or 7)
            res_eff = str(bundle_vp.get("resolution") or "480x480")
        elif montage_preset == "kling_v3_reference_motion":
            mid = _KLING_V3_STD_MODEL_ID
            backend = "openrouter"
            openrouter_model = _KLING_V3_STD_MODEL_ID
            i2v_model = "wan2.7-i2v"
            pm = "first_frame_only"
            audio_req = False
            dur = int(bundle_vp.get("duration_sec") or 5)
            res_eff = str(bundle_vp.get("resolution") or "720x720")
        await _upsert_active_profile_video_policy(
            backend=backend,
            i2v_model=i2v_model,
            openrouter_model=openrouter_model,
            prompt_mode=pm,
            montage_preset=montage_preset,
            audio_required=audio_req,
            duration_sec=dur,
            resolution=res_eff,
        )
        active = dream_lite_run_repo.get_active_profile_sync() if dream_lite_run_repo else {}
        rev = int((active or {}).get("profile_revision") or 0)
        return HTMLResponse(
            f'<p class="dream-lite-secondary">Active Tool (video) обновлён: <code>{html.escape(mid)}</code> · backend <code>{html.escape(backend)}</code> · montage_preset <code>{html.escape(montage_preset)}</code> · revision <code>{rev}</code>. '
            + (f"effective_prompt_policy=<code>{html.escape(effective_policy)}</code>. ")
            + ("Режим Seedance + native audio: ручные overrides model/prompt_mode игнорируются сервером. " if locked_effective else "")
            + "Новые запуски Playground и Telegram будут использовать эту видео-конфигурацию.</p>"
        )

    @router.get("/partials/dream/pipeline_lite_workers_tab", response_class=HTMLResponse)
    async def partial_dream_pipeline_lite_workers_tab(request: Request) -> Any:
        resp = _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_workers_tab.html",
            {"stage_contracts": stage_contract_catalog()},
        )
        resp.headers["Cache-Control"] = "no-store"
        return resp

    async def _auto_fail_stale_active_runs_for_live(*, user_id: int | None = None, max_idle_seconds: int = 900) -> int:
        if dream_lite_run_repo is None:
            return 0
        total = 0
        if user_id is not None:
            total += await dream_lite_run_repo.fail_stale_active_runs(
                user_id=int(user_id),
                max_idle_seconds=max_idle_seconds,
                reason="auto_fail_stale_active_run_from_live_view",
            )
            return total
        recent = dream_lite_run_repo.list_recent_runs_sync(limit=80)
        seen_users: set[int] = set()
        for row in recent:
            try:
                su = int(row.get("user_id") or 0)
            except Exception:
                su = 0
            if su <= 0 or su in seen_users:
                continue
            seen_users.add(su)
            total += await dream_lite_run_repo.fail_stale_active_runs(
                user_id=su,
                max_idle_seconds=max_idle_seconds,
                reason="auto_fail_stale_active_run_from_live_view",
            )
        return total

    def _lite_runs_live_ctx(*, user_id: int | None = None, stale_info: str = "") -> dict[str, Any]:
        def _ui_url(raw: str | None) -> str:
            u = str(raw or "").strip()
            if not u:
                return ""
            if u.startswith(("http://", "https://")):
                return u
            if u.startswith("/dev/"):
                base = (settings.public_base_url or "").strip().rstrip("/")
                return f"{base}{u}" if base else u
            return u

        def _anim_total(doc: dict[str, Any]) -> int:
            plan = doc.get("transition_plan") or {}
            trs = list(plan.get("transitions") or [])
            total = 0
            for t in trs:
                kind = str((t or {}).get("type") or "").strip().lower()
                if kind == "animate_transition":
                    total += 1
            if total > 0:
                return total
            return len(list(doc.get("generated_anim_clips") or []))

        runs_raw: list[dict[str, Any]] = []
        if dream_lite_run_repo is not None:
            try:
                runs_raw = dream_lite_run_repo.list_recent_runs_sync(limit=60, user_id=user_id)
            except Exception:
                runs_raw = []
        runs: list[dict[str, Any]] = []
        model_daily: dict[str, dict[str, Any]] = {}
        now_ts = datetime.now(timezone.utc).timestamp()
        stale_sec = 900
        for d in runs_raw:
            ua = d.get("updated_at")
            ua_str = ua.isoformat() if hasattr(ua, "isoformat") else str(ua or "")
            try:
                ua_ts = float(ua.timestamp()) if hasattr(ua, "timestamp") else 0.0
            except Exception:
                ua_ts = 0.0
            idle_seconds = int(max(0, now_ts - ua_ts)) if ua_ts > 0 else 0
            run_status = str(d.get("run_status") or "unknown").strip().lower()
            is_stale_active = bool(run_status == "active" and idle_seconds >= stale_sec)
            err = str(d.get("last_error") or "").strip()
            runs.append(
                {
                    "lite_run_id": str(d.get("lite_run_id") or ""),
                    "user_id": int(d.get("user_id") or 0),
                    "run_status": run_status,
                    "step_phase": str(d.get("step_phase") or "").strip(),
                    "updated_at_str": ua_str,
                    "idle_seconds": idle_seconds,
                    "is_stale_active": is_stale_active,
                    "last_error_short": err[:220] + ("…" if len(err) > 220 else ""),
                    "gen_env_i": int(d.get("gen_env_i") or 0),
                    "env_total": len(list(d.get("env_cards") or [])),
                    "gen_char_i": int(d.get("gen_char_i") or 0),
                    "char_total": len(list(d.get("char_cards") or [])),
                    "gen_frame_i": int(d.get("gen_frame_i") or 0),
                    "frame_total": len(list(d.get("frame_cards") or [])),
                    "gen_anim_i": int(d.get("gen_anim_i") or 0),
                    "anim_total": _anim_total(d),
                    "final_video_url": str(d.get("final_video_url") or "").strip(),
                    "final_video_url_ui": _ui_url(str(d.get("final_video_url") or "").strip()),
                    "images_ready": sum(
                        1
                        for fr in list(d.get("generated_frames") or [])
                        if isinstance(fr, dict) and list(fr.get("urls") or [])
                    ),
                    "videos_ready": sum(
                        1
                        for cl in list(d.get("generated_anim_clips") or [])
                        if isinstance(cl, dict) and str(cl.get("video_url") or "").strip()
                    ),
                    "first_image_url": next(
                        (
                            str((fr.get("urls") or [None])[0] or "").strip()
                            for fr in list(d.get("generated_frames") or [])
                            if isinstance(fr, dict) and list(fr.get("urls") or [])
                        ),
                        "",
                    ),
                    "first_video_url": next(
                        (
                            str(cl.get("video_url") or "").strip()
                            for cl in list(d.get("generated_anim_clips") or [])
                            if isinstance(cl, dict) and str(cl.get("video_url") or "").strip()
                        ),
                        "",
                    ),
                    "first_image_url_ui": _ui_url(
                        next(
                            (
                                str((fr.get("urls") or [None])[0] or "").strip()
                                for fr in list(d.get("generated_frames") or [])
                                if isinstance(fr, dict) and list(fr.get("urls") or [])
                            ),
                            "",
                        )
                    ),
                    "first_video_url_ui": _ui_url(
                        next(
                            (
                                str(cl.get("video_url") or "").strip()
                                for cl in list(d.get("generated_anim_clips") or [])
                                if isinstance(cl, dict) and str(cl.get("video_url") or "").strip()
                            ),
                            "",
                        )
                    ),
                }
            )
            for ev in list(d.get("execution_trace") or []):
                if not isinstance(ev, dict) or str(ev.get("event") or "") != "image_frame_generated":
                    continue
                model = str(ev.get("model") or ev.get("requested_model") or "").strip() or "unknown"
                row = model_daily.setdefault(model, {"model": model, "runs_count": 0, "total_duration_ms": 0, "samples": 0, "total_tokens": 0, "usage_unavailable": 0})
                row["runs_count"] = int(row["runs_count"]) + 1
                dur = int(ev.get("duration_ms") or 0)
                row["total_duration_ms"] = int(row["total_duration_ms"]) + max(0, dur)
                row["samples"] = int(row["samples"]) + 1
                tt = int(ev.get("total_tokens") or 0)
                row["total_tokens"] = int(row["total_tokens"]) + max(0, tt)
                if tt <= 0:
                    row["usage_unavailable"] = int(row["usage_unavailable"]) + 1
        daily_rows = []
        for row in model_daily.values():
            samples = int(row.get("samples") or 0) or 1
            avg_dur = int((int(row.get("total_duration_ms") or 0)) / samples)
            daily_rows.append(
                {
                    "model": row["model"],
                    "runs_count": int(row.get("runs_count") or 0),
                    "avg_duration_ms": avg_dur,
                    "total_tokens": int(row.get("total_tokens") or 0),
                    "estimated_cost_usd_total": None,
                    "usage_unavailable": bool(int(row.get("usage_unavailable") or 0) >= int(row.get("runs_count") or 0)),
                }
            )
        daily_rows.sort(key=lambda x: x["runs_count"], reverse=True)
        return {"runs": runs, "stale_info": stale_info, "daily_model_stats": daily_rows}

    def _lite_stage_rows(phase: str, run_status: str) -> list[dict[str, str]]:
        order = [
            "text_step1",
            "text_step2",
            "gen_env",
            "gen_char",
            "gen_frame",
            "transition_plan",
            "anim_i2v",
            "finalize_clips",
            "completed",
        ]
        idx = order.index(phase) if phase in order else -1
        rows: list[dict[str, str]] = []
        for i, st in enumerate(order):
            state = "pending"
            if i < idx:
                state = "completed"
            elif i == idx:
                state = "running"
            rows.append({"id": st, "state": state})
        if run_status == "failed":
            if idx >= 0:
                rows[idx]["state"] = "failed"
            else:
                rows.append({"id": "failed", "state": "failed"})
        if run_status == "completed":
            for r in rows:
                if r["id"] == "completed":
                    r["state"] = "completed"
        return rows

    def _build_run_detail_context_full(run: dict[str, Any]) -> dict[str, Any]:
        contract_map = {str(x.get("stage") or ""): x for x in stage_contract_catalog()}

        def _effective_step_requests(run_doc: dict[str, Any]) -> list[dict[str, Any]]:
            rc = run_doc.get("run_config") if isinstance(run_doc.get("run_config"), dict) else {}
            steps_cfg = rc.get("steps") if isinstance(rc.get("steps"), dict) else {}
            image_policy = rc.get("image_policy") if isinstance(rc.get("image_policy"), dict) else {}
            video_policy = rc.get("video_policy") if isinstance(rc.get("video_policy"), dict) else {}
            fallback_policy = rc.get("fallback_policy") if isinstance(rc.get("fallback_policy"), dict) else {}

            rows: list[dict[str, Any]] = []

            def add_row(stage: str, prompt_source: str, payload: dict[str, Any]) -> None:
                rows.append(
                    {
                        "stage": stage,
                        "contract": contract_map.get(stage) or {},
                        "prompt_source": prompt_source,
                        "payload": payload,
                    }
                )

            add_row(
                "text_step1",
                "prompts/dream_pipeline_lite_environments.md",
                {
                    "model": steps_cfg.get("text_step1_model") or "",
                    "provider": steps_cfg.get("text_step1_provider") or "openai_chat",
                    "inputs": ["dream_text"],
                },
            )
            add_row(
                "text_step2",
                "prompts/dream_pipeline_lite_frames.md + prompts/dream_pipeline_lite_frames_prev_link.md",
                {
                    "model": steps_cfg.get("text_step2_model") or "",
                    "provider": steps_cfg.get("text_step2_provider") or "openai_chat",
                    "inputs": ["dream_text", "step1_markdown"],
                },
            )
            add_row(
                "gen_env",
                "generated prompt in worker",
                {
                    "provider": image_policy.get("provider") or "openrouter",
                    "model": image_policy.get("model") or "",
                    "mode": image_policy.get("mode") or "text",
                },
            )
            add_row(
                "gen_char",
                "generated prompt in worker",
                {
                    "provider": image_policy.get("provider") or "openrouter",
                    "model": image_policy.get("model") or "",
                    "mode": image_policy.get("mode") or "text",
                },
            )
            add_row(
                "gen_frame",
                "generated prompt in worker + frame refs",
                {
                    "provider": image_policy.get("provider") or "openrouter",
                    "model": image_policy.get("model") or "",
                    "mode": image_policy.get("mode") or "text+image_refs",
                },
            )
            add_row(
                "transition_plan",
                (
                    "prompts/dream_pipeline_lite_transitions_seedance.md"
                    if str(video_policy.get("montage_preset") or "").strip() == "seedance"
                    else (
                        "prompts/dream_pipeline_lite_transitions_wan26.md"
                        if str(video_policy.get("montage_preset") or "").strip() == "wan_2_6_single_anchor"
                        else (
                            "prompts/dream_pipeline_lite_transitions_kling_v3_reference.md"
                            if str(video_policy.get("montage_preset") or "").strip() == "kling_v3_reference_motion"
                            else "prompts/dream_pipeline_lite_transitions.md"
                        )
                    )
                ),
                {
                    "model": steps_cfg.get("transition_plan_model") or "",
                    "provider": steps_cfg.get("transition_plan_provider") or "openai_chat",
                    "montage_preset": video_policy.get("montage_preset") or "default",
                    "inputs": ["frame_cards", "dream_text"],
                },
            )
            add_row(
                "anim_i2v",
                "segment motion_prompt + frame links",
                {
                    "provider_priority": video_policy.get("backend_priority") or ["dashscope", "openrouter"],
                    "mode": video_policy.get("mode") or "image+text",
                    "i2v_model": video_policy.get("i2v_model") or "wan2.7-i2v",
                    "duration_sec": video_policy.get("duration_sec") or 4,
                    "resolution": video_policy.get("resolution") or "720p",
                    "backend": video_policy.get("backend") or "",
                    "openrouter_model": video_policy.get("openrouter_model") or "",
                    "fallback": fallback_policy,
                },
            )
            add_row(
                "finalize_clips",
                "ffmpeg concat",
                {
                    "provider": "local_ffmpeg",
                    "inputs": ["generated_anim_clips.video_url[]"],
                },
            )
            return rows

        def _ui_url(raw: str | None) -> str:
            u = str(raw or "").strip()
            if not u:
                return ""
            if u.startswith(("http://", "https://")):
                return u
            if u.startswith("/dev/"):
                base = (settings.public_base_url or "").strip().rstrip("/")
                return f"{base}{u}" if base else u
            return u

        clips_raw = list(run.get("generated_anim_clips") or [])
        clips: list[dict[str, Any]] = []
        for c in clips_raw:
            status = str(c.get("status") or "unknown").strip().lower()
            status_ui = "running" if status in ("created", "running") else ("failed" if status in ("failed", "timeout") else ("completed" if status == "succeeded" else "pending"))
            err = str(c.get("error") or "").strip()
            clips.append(
                {
                    "segment_index": c.get("segment_index"),
                    "from_frame_index": c.get("from_frame_index"),
                    "to_frame_index": c.get("to_frame_index"),
                    "status": status or "unknown",
                    "status_ui": status_ui,
                    "video_url": str(c.get("video_url") or "").strip(),
                    "video_url_ui": _ui_url(str(c.get("video_url") or "").strip()),
                    "error_short": err[:180] + ("…" if len(err) > 180 else ""),
                }
            )
        frames_raw = list(run.get("generated_frames") or [])
        plan = run.get("transition_plan") or {}
        frame_usage: dict[int, list[str]] = {}
        for tr in list(plan.get("transitions") or []):
            if not isinstance(tr, dict):
                continue
            try:
                fi = int(tr.get("from_frame_index"))
                ti = int(tr.get("to_frame_index"))
            except (TypeError, ValueError):
                continue
            tr_type = str(tr.get("transition_type") or tr.get("type") or "unknown").strip()
            seg_mode = str(tr.get("segment_mode") or "pairwise").strip() or "pairwise"
            tag = f"{fi}->{ti}:{tr_type}:{seg_mode}"
            frame_usage.setdefault(fi, []).append(tag)
            frame_usage.setdefault(ti, []).append(tag)
        frames: list[dict[str, Any]] = []
        for fr in frames_raw:
            urls = list(fr.get("urls") or [])
            idx_val = fr.get("index")
            try:
                idx_int = int(idx_val) if idx_val is not None else None
            except (TypeError, ValueError):
                idx_int = None
            frames.append(
                {
                    "index": idx_val,
                    "title": str(fr.get("title") or ""),
                    "ok": bool(fr.get("ok")),
                    "img_url": str(urls[0]).strip() if urls else "",
                    "img_url_ui": _ui_url(str(urls[0]).strip() if urls else ""),
                    "error": str(fr.get("error") or "").strip(),
                    "used_in_transition_segments": list(frame_usage.get(idx_int, [])) if idx_int is not None else [],
                }
            )
        run_view = {
            "lite_run_id": str(run.get("lite_run_id") or ""),
            "user_id": int(run.get("user_id") or 0),
            "run_status": str(run.get("run_status") or "unknown").strip().lower(),
            "step_phase": str(run.get("step_phase") or "").strip(),
            "gen_env_i": int(run.get("gen_env_i") or 0),
            "env_total": len(list(run.get("env_cards") or [])),
            "gen_char_i": int(run.get("gen_char_i") or 0),
            "char_total": len(list(run.get("char_cards") or [])),
            "gen_frame_i": int(run.get("gen_frame_i") or 0),
            "frame_total": len(list(run.get("frame_cards") or [])),
            "gen_anim_i": int(run.get("gen_anim_i") or 0),
            "anim_total": sum(
                1
                for t in list((run.get("transition_plan") or {}).get("transitions") or [])
                if str((t or {}).get("type") or "").strip().lower() == "animate_transition"
            ) or len(list(run.get("generated_anim_clips") or [])),
            "final_video_url": str(run.get("final_video_url") or "").strip(),
            "final_video_url_ui": _ui_url(str(run.get("final_video_url") or "").strip()),
            "final_assembly_error": str(run.get("final_assembly_error") or "").strip(),
            "last_error": str(run.get("last_error") or "").strip(),
            "dream_text": str(run.get("dream_text") or ""),
            "step1_raw": str(run.get("step1_raw") or ""),
            "step2_raw": str(run.get("step2_raw") or ""),
            "step2_prev_link_raw": str(run.get("step2_prev_link_raw") or ""),
            "transition_plan_raw": str(run.get("transition_plan_raw") or ""),
        }
        editable_payload = {
            "dream_text": run_view["dream_text"],
            "step1_raw": run_view["step1_raw"],
            "step2_raw": run_view["step2_raw"],
            "step2_prev_link_raw": run_view["step2_prev_link_raw"],
            "transition_plan_raw": run_view["transition_plan_raw"],
        }
        details_payload = {
            "env_cards": list(run.get("env_cards") or []),
            "char_cards": list(run.get("char_cards") or []),
            "frame_cards": list(run.get("frame_cards") or []),
            "generated_env": dict(run.get("generated_env") or {}),
            "generated_char": dict(run.get("generated_char") or {}),
            "transition_plan": run.get("transition_plan") or {},
            "failed_transitions": list(run.get("failed_transitions") or []),
        }
        trace_rows: list[dict[str, Any]] = []
        for e in list(run.get("execution_trace") or []):
            if not isinstance(e, dict):
                continue
            ts = e.get("ts")
            ts_s = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")
            trace_rows.append(
                {
                    "ts": ts_s,
                    "event": str(e.get("event") or "").strip(),
                    "phase": str(e.get("phase") or "").strip(),
                    "model": str(e.get("model") or "").strip(),
                    "provider": str(e.get("provider") or e.get("backend") or "").strip(),
                    "status": str(e.get("status") or "").strip(),
                    "job_id": str(e.get("job_id") or "").strip(),
                    "fallback": str(e.get("fallback") or "").strip(),
                    "error": str(e.get("error") or "").strip(),
                }
            )
        generated_env_items = []
        for title, slot in dict(run.get("generated_env") or {}).items():
            s = slot if isinstance(slot, dict) else {}
            urls = list(s.get("urls") or [])
            generated_env_items.append(
                {
                    "title": str(title),
                    "ok": bool(s.get("ok")),
                    "image_url": str(urls[0]).strip() if urls else "",
                    "image_url_ui": _ui_url(str(urls[0]).strip() if urls else ""),
                    "error": str(s.get("error") or "").strip(),
                }
            )
        generated_char_items = []
        for title, slot in dict(run.get("generated_char") or {}).items():
            s = slot if isinstance(slot, dict) else {}
            urls = list(s.get("urls") or [])
            generated_char_items.append(
                {
                    "title": str(title),
                    "ok": bool(s.get("ok")),
                    "image_url": str(urls[0]).strip() if urls else "",
                    "image_url_ui": _ui_url(str(urls[0]).strip() if urls else ""),
                    "error": str(s.get("error") or "").strip(),
                }
            )
        transition_rows: list[dict[str, Any]] = []
        for t in list(plan.get("transitions") or []):
            if not isinstance(t, dict):
                continue
            typ = str(t.get("transition_type") or t.get("type") or "").strip()
            transition_rows.append(
                {
                    "from_frame_index": t.get("from_frame_index"),
                    "to_frame_index": t.get("to_frame_index"),
                    "transition_type": typ or "unknown",
                    "segment_mode": str(t.get("segment_mode") or "pairwise").strip() or "pairwise",
                    "motion_prompt": str(t.get("motion_prompt") or "").strip(),
                    "cut_reason": str(t.get("cut_reason") or "").strip(),
                }
            )
        scene_rows: list[dict[str, Any]] = []
        for s in list(plan.get("scenes") or []):
            if not isinstance(s, dict):
                continue
            scene_rows.append(
                {
                    "scene_index": s.get("scene_index"),
                    "from_frame_index": s.get("from_frame_index"),
                    "to_frame_index": s.get("to_frame_index"),
                    "scene_type": str(s.get("scene_type") or "").strip(),
                    "note": str(s.get("note") or "").strip(),
                }
            )
        return {
            "run": run_view,
            "stage_rows": _lite_stage_rows(run_view["step_phase"], run_view["run_status"]),
            "clips": clips,
            "frames": frames,
            "env_cards": list(run.get("env_cards") or []),
            "char_cards": list(run.get("char_cards") or []),
            "frame_cards": list(run.get("frame_cards") or []),
            "generated_env_items": generated_env_items,
            "generated_char_items": generated_char_items,
            "transition_rows": transition_rows,
            "scene_rows": scene_rows,
            "transition_plan_json": json.dumps(run.get("transition_plan") or {}, ensure_ascii=False, indent=2),
            "failed_transitions": list(run.get("failed_transitions") or []),
            "pipeline_variant": str(run.get("pipeline_variant") or "pair_i2v_between_keyframes"),
            "config_profile_name": str(run.get("config_profile_name") or "default_fallback"),
            "config_profile_revision": int(run.get("config_profile_revision") or 0),
            "run_config_json": json.dumps(run.get("run_config") or {}, ensure_ascii=False, indent=2),
            "effective_step_requests": _effective_step_requests(run),
            "trace_rows": trace_rows,
            "editable_payload_json": json.dumps(editable_payload, ensure_ascii=False, indent=2),
            "details_payload_json": json.dumps(details_payload, ensure_ascii=False, indent=2),
            "save_info": "",
        }

    @router.get("/partials/dream/lite/runs_live", response_class=HTMLResponse)
    async def partial_dream_lite_runs_live(request: Request) -> Any:
        auto_total = await _auto_fail_stale_active_runs_for_live()
        auto_info = f"Авто-сброс зависших active run: {auto_total}" if auto_total > 0 else ""
        resp = _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_live_runs.html",
            _lite_runs_live_ctx(stale_info=auto_info),
        )
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @router.get("/dream/lite/live_runs", response_class=HTMLResponse)
    async def page_dream_lite_live_runs(request: Request) -> Any:
        auto_total = await _auto_fail_stale_active_runs_for_live()
        auto_info = f"Авто-сброс зависших active run: {auto_total}" if auto_total > 0 else ""
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_live_runs_page.html",
            _lite_runs_live_ctx(stale_info=auto_info),
        )

    @router.post("/api/dream/lite/runs/fail_stale", response_class=HTMLResponse)
    async def api_dream_lite_fail_stale_runs(
        request: Request,
        user_id: str = Form(""),
    ) -> Any:
        if dream_lite_run_repo is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_live_runs.html",
                {"runs": [], "stale_info": "DreamLiteRunRepository не подключён."},
            )
        uid_raw = (user_id or "").strip()
        uid: int | None = None
        if uid_raw:
            try:
                uid = int(uid_raw)
            except ValueError:
                uid = None
        total = 0
        if uid is not None:
            total += await dream_lite_run_repo.fail_stale_active_runs(
                user_id=uid,
                max_idle_seconds=900,
                reason="manual_fail_stale_active_run_from_dev_ui",
            )
        else:
            # Без user_id чистим последних пользователей из live-таблицы.
            recent = dream_lite_run_repo.list_recent_runs_sync(limit=80)
            seen_users: set[int] = set()
            for row in recent:
                try:
                    su = int(row.get("user_id") or 0)
                except Exception:
                    su = 0
                if su <= 0 or su in seen_users:
                    continue
                seen_users.add(su)
                total += await dream_lite_run_repo.fail_stale_active_runs(
                    user_id=su,
                    max_idle_seconds=900,
                    reason="manual_fail_stale_active_run_from_dev_ui",
                )
        info = f"Сброшено зависших active run: {total}"
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_live_runs.html",
            _lite_runs_live_ctx(user_id=uid, stale_info=info),
        )

    @router.get("/partials/dream/lite/run_detail", response_class=HTMLResponse)
    async def partial_dream_lite_run_detail(
        request: Request,
        user_id: int = Query(...),
        lite_run_id: str = Query(...),
    ) -> Any:
        if dream_lite_run_repo is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_run_detail.html",
                {"run": None, "stage_rows": [], "clips": [], "failed_transitions": [], "frames": []},
            )
        run = dream_lite_run_repo.get_run_sync(user_id=user_id, lite_run_id=lite_run_id)
        if not run:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_run_detail.html",
                {"run": None, "stage_rows": [], "clips": [], "failed_transitions": [], "frames": []},
            )
        resp = _TEMPLATES.TemplateResponse(request, "partials/dream_pipeline_lite_run_detail.html", _build_run_detail_context_full(run))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @router.get("/dream/lite/run_inspector", response_class=HTMLResponse)
    async def page_dream_lite_run_inspector(
        request: Request,
        user_id: int = Query(...),
        lite_run_id: str = Query(...),
    ) -> Any:
        if dream_lite_run_repo is None:
            return HTMLResponse("DreamLiteRunRepository не подключён.", status_code=503)
        run = dream_lite_run_repo.get_run_sync(user_id=user_id, lite_run_id=lite_run_id)
        if not run:
            return HTMLResponse("Run не найден.", status_code=404)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_run_detail_page.html",
            _build_run_detail_context_full(run),
        )

    @router.post("/api/dream/lite/run_patch", response_class=HTMLResponse)
    async def api_dream_lite_run_patch(
        request: Request,
        user_id: int = Form(...),
        lite_run_id: str = Form(...),
        patch_json: str = Form(""),
    ) -> Any:
        if dream_lite_run_repo is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_run_detail.html",
                {"run": None, "stage_rows": [], "clips": [], "failed_transitions": [], "frames": [], "save_info": "DreamLiteRunRepository не подключён."},
            )
        run = dream_lite_run_repo.get_run_sync(user_id=user_id, lite_run_id=lite_run_id)
        if not run:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_run_detail.html",
                {"run": None, "stage_rows": [], "clips": [], "failed_transitions": [], "frames": [], "save_info": "Run не найден."},
            )
        info = "Сохранено."
        allowed_fields = {
            "dream_text",
            "step1_raw",
            "step2_raw",
            "step2_prev_link_raw",
            "transition_plan_raw",
        }
        patch: dict[str, Any] = {}
        try:
            parsed = json.loads((patch_json or "").strip() or "{}")
            if not isinstance(parsed, dict):
                raise ValueError("patch_json должен быть JSON-объектом")
            for k, v in parsed.items():
                if k not in allowed_fields:
                    continue
                patch[k] = str(v or "")
            if not patch:
                info = "Нет изменений для сохранения (разрешены только dream_text/step*_raw/transition_plan_raw)."
            else:
                await dream_lite_run_repo.update_run(user_id=user_id, lite_run_id=lite_run_id, patch=patch)
        except Exception as exc:
            info = f"Ошибка сохранения: {exc}"

        fresh = dream_lite_run_repo.get_run_sync(user_id=user_id, lite_run_id=lite_run_id) or run
        ctx = _build_run_detail_context_full(fresh)
        ctx["save_info"] = info
        return _TEMPLATES.TemplateResponse(request, "partials/dream_pipeline_lite_run_detail.html", ctx)

    @router.post("/api/dream/lite/profile/activate_from_run")
    async def api_dream_lite_profile_activate_from_run(
        user_id: int = Form(...),
        lite_run_id: str = Form(...),
    ) -> Any:
        """Сделать run_config выбранного run активным эталоном для новых запусков (Playground + Telegram)."""
        if dream_lite_run_repo is None:
            raise HTTPException(status_code=503, detail="dream_lite_run_repo not configured")
        run = dream_lite_run_repo.get_run_sync(user_id=user_id, lite_run_id=lite_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        run_config = run.get("run_config")
        if not isinstance(run_config, dict) or not run_config:
            raise HTTPException(status_code=400, detail="run has empty run_config")
        ok = await dream_lite_run_repo.upsert_active_profile(
            run_config=run_config,
            pipeline_variant=str(run.get("pipeline_variant") or "").strip() or None,
            updated_by_user_id=user_id,
            profile_name="default",
        )
        if not ok:
            raise HTTPException(status_code=500, detail="failed to activate profile")
        return HTMLResponse(
            "<span class='dream-lite-save-ok'>Эталон обновлён: profile=default, "
            f"source={int(user_id)}:{html.escape(str(lite_run_id or '').strip())}</span>"
        )

    @router.get("/api/dream/lite/parity_check")
    async def api_dream_lite_parity_check() -> Any:
        """Быстрая проверка parity между Playground и Telegram runtime-инструментом."""
        runtime_tools = get_tools_for_runtime(data_dir=settings.data_dir)
        if not runtime_tools:
            runtime_tools = list(OPENAI_TOOLS_DEFAULT)
        runtime_tool_names = [
            str((t.get("function") or {}).get("name") or "").strip()
            for t in runtime_tools
            if str((t.get("function") or {}).get("name") or "").strip()
        ]
        has_main_tool = "generate_dream_pipeline" in runtime_tool_names
        active_profile = dream_lite_run_repo.get_active_profile_sync() if dream_lite_run_repo else None
        active_revision = int((active_profile or {}).get("profile_revision") or 0)
        active_variant = str((active_profile or {}).get("pipeline_variant") or "").strip()
        parity_ok = bool(has_main_tool) and bool(active_profile)
        return JSONResponse(
            {
                "ok": parity_ok,
                "checks": {
                    "runtime_has_generate_dream_pipeline": has_main_tool,
                    "active_profile_present": bool(active_profile),
                    "playground_user_id": int(settings.dream_lite_playground_user_id),
                    "module_playground_user_id": int(LITE_PLAYGROUND_USER_ID),
                },
                "runtime_tools": runtime_tool_names,
                "active_profile": {
                    "profile_name": str((active_profile or {}).get("profile_name") or ""),
                    "profile_revision": active_revision,
                    "pipeline_variant": active_variant,
                    "image_model": str(
                        (
                            ((active_profile or {}).get("run_config") or {}).get("image_policy")
                            if isinstance(((active_profile or {}).get("run_config") or {}).get("image_policy"), dict)
                            else {}
                        ).get("model")
                        or ""
                    ),
                },
            }
        )

    @router.get("/api/dream/lite/model_registry")
    async def api_dream_lite_model_registry() -> Any:
        return JSONResponse({"ok": True, "models": model_capability_registry()})

    @router.post("/api/dream/lite/contract_preview")
    async def api_dream_lite_contract_preview(
        model_id: str = Form(""),
        task_type: str = Form(""),
        prompt: str = Form(""),
        negative_prompt: str = Form(""),
        first_frame: str = Form(""),
        last_frame: str = Form(""),
        reference_images_json: str = Form("[]"),
        duration: str = Form(""),
        resolution: str = Form(""),
        aspect_ratio: str = Form(""),
        camera_motion: str = Form(""),
        scene_id: str = Form(""),
        step_id: str = Form(""),
    ) -> Any:
        profile = get_model_profile(model_id)
        if not profile:
            raise HTTPException(status_code=404, detail="model profile not found")
        refs: list[str] = []
        try:
            parsed = json.loads((reference_images_json or "").strip() or "[]")
            if isinstance(parsed, list):
                refs = [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            refs = []
        payload = {
            "task_type": (task_type or "").strip() or str(profile.get("task_type") or ""),
            "prompt": (prompt or "").strip(),
            "negative_prompt": (negative_prompt or "").strip(),
            "first_frame": (first_frame or "").strip(),
            "last_frame": (last_frame or "").strip(),
            "reference_images": refs,
            "duration": int(duration) if (duration or "").strip().isdigit() else None,
            "resolution": (resolution or "").strip(),
            "aspect_ratio": (aspect_ratio or "").strip(),
            "camera_motion": (camera_motion or "").strip(),
            "scene_id": (scene_id or "").strip(),
            "step_id": (step_id or "").strip(),
        }
        preview = build_provider_request_from_internal_payload(
            internal_payload=payload,
            model_profile=profile,
        )
        return JSONResponse({"ok": True, **preview})

    @router.post("/api/dream/lite/dry_run_contract")
    async def api_dream_lite_dry_run_contract(
        model_id: str = Form(""),
        internal_payload_json: str = Form("{}"),
    ) -> Any:
        profile = get_model_profile(model_id)
        if not profile:
            return JSONResponse({"ok": False, "status": "Error", "errors": ["model profile not found"], "warnings": []}, status_code=404)
        try:
            payload = json.loads((internal_payload_json or "").strip() or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except json.JSONDecodeError:
            payload = {}
        preview = build_provider_request_from_internal_payload(internal_payload=payload, model_profile=profile)
        status = "OK" if preview.get("ok") else "Error"
        if preview.get("warnings") and preview.get("ok"):
            status = "Warning"
        return JSONResponse(
            {
                "ok": bool(preview.get("ok")),
                "status": status,
                "errors": list(preview.get("errors") or []),
                "warnings": list(preview.get("warnings") or []),
                "provider_request": preview.get("provider_request") or {},
                "text": "PROVIDER WILL NOT BE CALLED.",
            }
        )

    @router.post("/api/dream/lite/dry_run_ui")
    async def api_dream_lite_dry_run_ui(
        model_id: str = Form(""),
        internal_payload_json: str = Form("{}"),
    ) -> Any:
        active_profile = dream_lite_run_repo.get_active_profile_sync() if dream_lite_run_repo else {}
        run_cfg = active_profile.get("run_config") if isinstance(active_profile.get("run_config"), dict) else {}
        profile = get_model_profile(model_id)
        if not profile:
            return JSONResponse({"ok": False, "status": "Error", "errors": ["model profile not found"], "warnings": []}, status_code=404)
        try:
            payload = json.loads((internal_payload_json or "").strip() or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except json.JSONDecodeError:
            payload = {}
        preview = build_provider_request_from_internal_payload(internal_payload=payload, model_profile=profile)
        return JSONResponse(
            {
                "ok": bool(preview.get("ok")),
                "status": "OK" if preview.get("ok") else "Error",
                "errors": list(preview.get("errors") or []),
                "warnings": list(preview.get("warnings") or []),
                "ui_payload": payload,
                "runtime_config_snapshot": run_cfg,
                "provider_request": preview.get("provider_request") or {},
                "text": "PROVIDER WILL NOT BE CALLED.",
            }
        )

    @router.post("/api/dream/lite/frame_image_contract_preview", response_class=HTMLResponse)
    async def api_dream_lite_frame_image_contract_preview(
        lite_run_id: str = Form(""),
        model_id: str = Form(""),
        user_id: str = Form(""),
        frame_index: str = Form("0"),
    ) -> Any:
        """Минимальный Live Contract Preview: contract + final provider JSON."""
        if dream_lite_run_repo is None:
            return HTMLResponse(
                '<p class="dream-lite-secondary">dream_lite_run_repo не настроен</p>',
                status_code=503,
            )
        uid = int(user_id) if (user_id or "").strip().isdigit() else int(settings.dream_lite_playground_user_id)
        rid = (lite_run_id or "").strip()
        if not rid and dream_lite_run_repo is not None:
            latest = dream_lite_run_repo.list_recent_runs_sync(limit=1, user_id=uid)
            if latest:
                rid = str((latest[0] or {}).get("lite_run_id") or "").strip()
        try:
            fi = int((frame_index or "0").strip() or "0")
        except ValueError:
            fi = 0
        run = dream_lite_run_repo.get_run_sync(user_id=uid, lite_run_id=rid) if rid else None
        override = (model_id or "").strip() or None
        if run:
            bundle = build_lite_frame_image_preview_bundle(
                run,
                fi,
                image_model_override=override,
                preview_mode="resolved",
            )
        else:
            bundle = {
                "ok": True,
                "frame_title": "preview_without_run",
                "image_model_resolved": override,
                "internal_payload": {
                    "task_type": "text_to_image",
                    "frame_index": 0,
                    "prompt": "Story frame prompt placeholder",
                    "reference_images": [],
                    "aspect_ratio": "9:16",
                    "resolution": "1K",
                    "policies": {
                        "use_previous_frame": False,
                        "prev_continuity_policy": "scene_aware_no_hard_limit",
                        "reference_priority": ["previous_frame", "environment", "character"],
                        "fallback_rules": {},
                    },
                },
            }
        mid_for_registry = (
            override
            or bundle.get("image_model_resolved")
            or "google/gemini-2.5-flash-image"
        )
        prof = get_model_profile(mid_for_registry)
        preview = (
            build_provider_request_from_internal_payload(
                internal_payload=bundle["internal_payload"],
                model_profile=prof,
            )
            if prof
            else None
        )

        def _pre(obj: Any) -> str:
            return html.escape(json.dumps(obj, ensure_ascii=False, indent=2))

        caps = (prof or {}).get("capabilities") if isinstance((prof or {}).get("capabilities"), dict) else {}
        lim = (prof or {}).get("limits") if isinstance((prof or {}).get("limits"), dict) else {}
        input_modalities = list((prof or {}).get("input_modalities") or ["text", "image"])
        output_modalities = list((prof or {}).get("output_modalities") or ((prof or {}).get("adapter_mapping") or {}).get("output_modalities") or ["image"])
        preview_status = str(
            (preview or {}).get("status")
            or ("blocked" if (preview or {}).get("errors") else ("degraded" if (preview or {}).get("warnings") else "full"))
        )
        degraded_reason = str((preview or {}).get("degraded_reason") or (prof or {}).get("degraded_reason") or "")
        adapter_result = {
            "accepted_fields": list((preview or {}).get("accepted_fields") or []),
            "dropped_fields": list((preview or {}).get("dropped_fields") or []),
            "inlined_fields": list((preview or {}).get("inlined_fields") or []),
            "missing_required_fields": list((preview or {}).get("missing_required_fields") or []),
            "warnings": list((preview or {}).get("warnings") or []),
            "errors": list((preview or {}).get("errors") or []),
        }
        all_warnings = list((preview or {}).get("warnings") or [])
        runtime_data_warnings = [w for w in all_warnings if str(w).startswith("missing required references (runtime data):")]
        model_warnings = [w for w in all_warnings if w not in runtime_data_warnings]
        adapter_result["warnings"] = model_warnings
        if runtime_data_warnings:
            adapter_result["runtime_data_warnings"] = runtime_data_warnings
        contract_view = {
            "model_id": mid_for_registry,
            "provider": str((prof or {}).get("provider") or "unknown"),
            "task_type": str((prof or {}).get("task_type") or "unknown"),
            "input_modalities": input_modalities,
            "output_modalities": output_modalities,
            "compatibility_status": preview_status,
            "degraded_reason": degraded_reason,
            "required_fields": list((prof or {}).get("required_fields") or []),
            "optional_fields": list((prof or {}).get("optional_fields") or []),
            "unsupported_fields_policy": dict((prof or {}).get("unsupported_fields_policy") or {}),
            "capabilities": caps,
            "limits": lim,
            "adapter_mapping": dict((prof or {}).get("adapter_mapping") or {}),
            "reference_priority": ((bundle.get("internal_payload") or {}).get("policies") or {}).get("reference_priority") or [],
        }
        provider_request_json = json.dumps((preview or {}).get("provider_request") or {}, ensure_ascii=False, indent=2)
        pr_id = f"dream-lite-provider-json-{fi}"

        blocks: list[str] = [
            '<article class="pipe-stage-card dream-lite-input-card dream-lite-debug-inner dream-lite-frame-contract">',
            f'<p class="dream-lite-secondary">Audit status: <span class="dream-lite-pill dream-lite-pill--{"ok" if preview_status == "full" else ("warn" if preview_status == "degraded" else "err")}">{html.escape(preview_status)}</span></p>',
            "<h5 class=\"dream-lite-secondary\">Model Contract</h5>",
            f'<pre class="dream-lite-textarea dream-lite-textarea--mono" style="max-height:260px;overflow:auto">{_pre(contract_view)}</pre>',
        ]
        if degraded_reason:
            blocks.append(f'<p class="dream-lite-secondary">degraded_reason: {html.escape(degraded_reason)}</p>')
        if not prof:
            blocks.append(
                f'<p class="dream-lite-secondary">Профиль registry для <code>{html.escape(mid_for_registry)}</code> не найден — добавьте модель в model_capability_registry.py.</p>'
            )
        elif preview:
            blocks.append("<h5 class=\"dream-lite-secondary\">Model Adapter Result</h5>")
            blocks.append(
                f'<pre class="dream-lite-textarea dream-lite-textarea--mono" style="max-height:220px;overflow:auto">{_pre(adapter_result)}</pre>'
            )
            blocks.append("<h5 class=\"dream-lite-secondary\">Final Provider JSON</h5>")
            if preview.get("errors"):
                blocks.append(
                    "<p class=\"dream-lite-secondary\">Contract errors: "
                    + html.escape(", ".join(str(x) for x in preview.get("errors") or []))
                    + "</p>"
                )
            if model_warnings:
                blocks.append(
                    "<p class=\"dream-lite-secondary\">warnings: "
                    + html.escape(", ".join(str(x) for x in model_warnings))
                    + "</p>"
                )
            if runtime_data_warnings:
                blocks.append(
                    "<p class=\"dream-lite-secondary\">runtime refs: "
                    + html.escape(", ".join(str(x) for x in runtime_data_warnings))
                    + "</p>"
                )
            blocks.append(
                f'<textarea id="{pr_id}" class="dream-lite-textarea dream-lite-textarea--mono" style="min-height:180px">{html.escape(provider_request_json)}</textarea>'
            )
            blocks.append(
                "<div class=\"dream-lite-actions\">"
                f"<button type=\"button\" class=\"btn-ghost\" onclick=\"navigator.clipboard.writeText(document.getElementById('{pr_id}').value)\">Copy Provider JSON</button>"
                "</div>"
            )
        if not run:
            blocks.append('<p class="dream-lite-secondary">Для точного кадра и референсов сначала выполните шаг 3 хотя бы один раз. Сейчас показан contract-only preview.</p>')
        blocks.append("</article>")
        return HTMLResponse("".join(blocks))

    @router.post("/api/dream/lite/config/apply_image_model", response_class=HTMLResponse)
    async def api_dream_lite_apply_image_model(model_id: str = Form("")) -> Any:
        mid = (model_id or "").strip()
        if not mid:
            return HTMLResponse('<p class="dream-lite-secondary">Выберите модель.</p>', status_code=400)
        await _upsert_active_profile_image_model(mid)
        active = dream_lite_run_repo.get_active_profile_sync() if dream_lite_run_repo else {}
        rev = int((active or {}).get("profile_revision") or 0)
        return HTMLResponse(
            f'<p class="dream-lite-secondary">Active Tool обновлён: <code>{html.escape(mid)}</code> · revision <code>{rev}</code>. '
            "Новые запуски Playground и Telegram будут использовать эту модель.</p>"
        )

    @router.post("/api/dream/lite/config/save_draft")
    async def api_dream_lite_save_draft() -> Any:
        if dream_lite_run_repo is None:
            raise HTTPException(status_code=503, detail="dream_lite_run_repo not configured")
        active = dream_lite_run_repo.get_active_profile_sync() or {}
        run_cfg = active.get("run_config") if isinstance(active.get("run_config"), dict) else default_run_config()
        ok = await dream_lite_run_repo.save_draft_profile(
            run_config=run_cfg,
            pipeline_variant=str(run_cfg.get("pipeline_variant") or "").strip() or None,
            updated_by_user_id=int(settings.dream_lite_playground_user_id),
            profile_name="default",
        )
        return JSONResponse({"ok": bool(ok), "status": "Draft"})

    @router.post("/api/dream/lite/config/publish_active")
    async def api_dream_lite_publish_active() -> Any:
        if dream_lite_run_repo is None:
            raise HTTPException(status_code=503, detail="dream_lite_run_repo not configured")
        ok = await dream_lite_run_repo.publish_draft_profile(
            profile_name="default",
            updated_by_user_id=int(settings.dream_lite_playground_user_id),
        )
        return JSONResponse({"ok": bool(ok), "status": "Active"})

    @router.post("/api/dream/lite/config/rollback")
    async def api_dream_lite_rollback() -> Any:
        if dream_lite_run_repo is None:
            raise HTTPException(status_code=503, detail="dream_lite_run_repo not configured")
        ok = await dream_lite_run_repo.rollback_active_profile(
            profile_name="default",
            updated_by_user_id=int(settings.dream_lite_playground_user_id),
        )
        return JSONResponse({"ok": bool(ok), "status": "Active"})

    @router.post("/api/dream/lite/paid_smoke_test")
    async def api_dream_lite_paid_smoke_test(
        model_id: str = Form(""),
        confirm: str = Form(""),
    ) -> Any:
        if (confirm or "").strip() != "RUN PAID SMOKE":
            return JSONResponse({"ok": False, "error": "confirm must be RUN PAID SMOKE"}, status_code=400)
        prof = get_model_profile(model_id)
        if not prof:
            return JSONResponse({"ok": False, "error": "model profile not found"}, status_code=404)
        task_type = str(prof.get("task_type") or "")
        if task_type == "text_to_image":
            r = tool_generate_image_openrouter(
                "minimal smoke test frame, simple object, neutral light",
                aspect_ratio="1:1",
                image_size="1K",
                model=model_id,
            ).to_dict()
            return JSONResponse({"ok": bool(r.get("ok")), "task_type": task_type, "result": r})
        return JSONResponse({"ok": False, "error": "paid smoke currently supports text_to_image model only"}, status_code=400)

    @router.post("/api/prompts/dream-pipeline-lite-environments-md", response_class=HTMLResponse)
    async def api_save_dream_pipeline_lite_environments_md(content: str = Form("")) -> Any:
        write_dream_pipeline_lite_environments_raw(content)
        await _upsert_active_profile_step_prompt("text_step1_system_prompt", content)
        return HTMLResponse(
            '<span class="dream-lite-save-ok">Сохранено: prompts/dream_pipeline_lite_environments.md</span>'
        )

    @router.post("/api/prompts/dream-pipeline-lite-environments-simple-md", response_class=HTMLResponse)
    async def api_save_dream_pipeline_lite_environments_simple_md(content: str = Form("")) -> Any:
        write_dream_pipeline_lite_environments_simple_raw(content)
        return HTMLResponse(
            '<span class="dream-lite-save-ok">Сохранено: prompts/dream_pipeline_lite_environments_simple.md</span>'
        )

    @router.post("/api/prompts/dream-pipeline-lite-frames-md", response_class=HTMLResponse)
    async def api_save_dream_pipeline_lite_frames_md(content: str = Form("")) -> Any:
        write_dream_pipeline_lite_frames_raw(content)
        await _upsert_active_profile_step_prompt("text_step2_system_prompt", content)
        return HTMLResponse(
            '<span class="dream-lite-save-ok">Сохранено: prompts/dream_pipeline_lite_frames.md</span>'
        )

    @router.post("/api/prompts/dream-pipeline-lite-frames-prev-link-md", response_class=HTMLResponse)
    async def api_save_dream_pipeline_lite_frames_prev_link_md(
        content: str = Form(""),
    ) -> Any:
        write_dream_pipeline_lite_frames_prev_link_raw(content)
        await _upsert_active_profile_step_prompt("text_step2_prev_link_system_prompt", content)
        return HTMLResponse(
            '<span class="dream-lite-save-ok">Сохранено: prompts/dream_pipeline_lite_frames_prev_link.md</span>'
        )

    @router.post("/api/prompts/dream-pipeline-lite-transitions-md", response_class=HTMLResponse)
    async def api_save_dream_pipeline_lite_transitions_md(content: str = Form("")) -> Any:
        write_dream_pipeline_lite_transitions_raw(content)
        await _upsert_active_profile_step_prompt("transition_plan_system_prompt", content)
        return HTMLResponse(
            '<span class="dream-lite-save-ok">Сохранено: prompts/dream_pipeline_lite_transitions.md</span>'
        )

    @router.post("/api/prompts/dream-pipeline-lite-transitions-seedance-md", response_class=HTMLResponse)
    async def api_save_dream_pipeline_lite_transitions_seedance_md(content: str = Form("")) -> Any:
        write_dream_pipeline_lite_transitions_seedance_raw(content)
        await _upsert_active_profile_step_prompt("transition_plan_seedance_system_prompt", content)
        return HTMLResponse(
            '<span class="dream-lite-save-ok">Сохранено: prompts/dream_pipeline_lite_transitions_seedance.md</span>'
        )

    @router.post("/api/prompts/dream-pipeline-lite-transitions-wan26-md", response_class=HTMLResponse)
    async def api_save_dream_pipeline_lite_transitions_wan26_md(content: str = Form("")) -> Any:
        write_dream_pipeline_lite_transitions_wan26_raw(content)
        await _upsert_active_profile_step_prompt("transition_plan_wan26_system_prompt", content)
        return HTMLResponse(
            '<span class="dream-lite-save-ok">Сохранено: prompts/dream_pipeline_lite_transitions_wan26.md</span>'
        )

    @router.post("/api/prompts/dream-pipeline-lite-transitions-kling-ref-md", response_class=HTMLResponse)
    async def api_save_dream_pipeline_lite_transitions_kling_ref_md(content: str = Form("")) -> Any:
        write_dream_pipeline_lite_transitions_kling_ref_raw(content)
        await _upsert_active_profile_step_prompt("transition_plan_kling_reference_system_prompt", content)
        return HTMLResponse(
            '<span class="dream-lite-save-ok">Сохранено: prompts/dream_pipeline_lite_transitions_kling_v3_reference.md</span>'
        )

    @router.post("/api/dream/lite/environments", response_class=HTMLResponse)
    async def api_dream_lite_environments(
        request: Request,
        dream_text: str = Form(""),
    ) -> Any:
        if dream_pipeline_service is None:
            return HTMLResponse(
                '<p class="error">Dream pipeline service не подключён.</p>',
                status_code=400,
            )
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            return HTMLResponse('<p class="error">OpenAI не сконфигурирован.</p>', status_code=400)
        if not (dream_text or "").strip():
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step_environments_result.html",
                {
                    "error": "Введите текст сна.",
                    "env_cards": [],
                    "char_cards": [],
                    "raw_text": "",
                },
            )
        try:
            steps_cfg = _active_lite_steps_cfg()
            raw_text = ""
            last_timeout: Exception | None = None
            for _attempt in range(2):
                try:
                    raw_text = await asyncio.wait_for(
                        lite_chat_text(
                            openai,
                            system=(str(steps_cfg.get("text_step1_system_prompt") or "").strip() or lite_environments_system_prompt()),
                            user=lite_environments_user_message(dream_text),
                        ),
                        timeout=60.0,
                    )
                    last_timeout = None
                    break
                except TimeoutError as exc:
                    last_timeout = exc
            if last_timeout is not None:
                raise last_timeout
        except TimeoutError:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step_environments_result.html",
                {
                    "error": "Шаг 1 превысил лимит времени (2 попытки по 60s). Это внешний timeout модели/сети; попробуйте еще раз.",
                    "env_cards": [],
                    "char_cards": [],
                    "raw_text": "",
                },
            )
        except Exception as exc:  # noqa: BLE001
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step_environments_result.html",
                {
                    "error": str(exc),
                    "env_cards": [],
                    "char_cards": [],
                    "raw_text": "",
                },
            )
        env_cards, char_cards = split_lite_step1_world(raw_text)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_step_environments_result.html",
            {
                "error": None,
                "env_cards": env_cards,
                "char_cards": char_cards,
                "raw_text": raw_text,
            },
        )

    def _dream_lite_visual_common_ctx() -> dict[str, Any]:
        return {
            "step3_phase": "complete",
            "frame_plans": None,
            "bases_bundle_json": "",
            "simple_mode": False,
            "image_models_catalog": _dream_lite_catalog_with_test_stats(),
        }

    def _form_bool(v: str | None) -> bool:
        s = (v or "").strip().lower()
        return s in {"1", "true", "yes", "on"}

    def _resolve_step3_image_model(image_model: str | None, *, simple_mode_on: bool) -> str:
        if simple_mode_on:
            return _SIMPLE_MODE_RECOMMENDED_IMAGE_MODEL
        return (image_model or "").strip() or (get_settings().openrouter_image_model or "").strip()

    @router.post("/api/dream/lite/generate_visuals_bases", response_class=HTMLResponse)
    async def api_dream_lite_generate_visuals_bases(
        request: Request,
        dream_text: str = Form(""),
        environments_text: str = Form(""),
        frames_text: str = Form(""),
        frames_prev_link_raw: str = Form(""),
        image_model: str = Form(""),
        simple_mode: str = Form(""),
    ) -> Any:
        simple_mode_on = _form_bool(simple_mode)
        empty_err: dict[str, Any] = {
            "error": None,
            "env_results": [],
            "char_results": [],
            "frame_results": [],
            "frames_for_step4_json": [],
            "step3_phase": "awaiting_frames",
            "frame_plans": [],
            "bases_bundle_json": "",
            "simple_mode": simple_mode_on,
            "image_models_catalog": _dream_lite_catalog_with_test_stats(),
            "selected_image_model": _resolve_step3_image_model(
                image_model,
                simple_mode_on=simple_mode_on,
            ),
        }
        if not (environments_text or "").strip():
            empty_err["error"] = "Нет текста шага 1 (окружения и персонажи). Сначала выполните шаг 1."
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                empty_err,
            )
        if not (frames_text or "").strip():
            empty_err["error"] = "Нет текста раскадровки. Сначала выполните шаг 2."
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                empty_err,
            )
        selected_model_id = _resolve_step3_image_model(
            image_model,
            simple_mode_on=simple_mode_on,
        )
        model_id = selected_model_id or None
        await _upsert_active_profile_image_policy(
            image_model=model_id,
            simple_mode=simple_mode_on,
        )
        try:
            env_results, char_results, url_by_env, url_by_char, env_order, char_order = (
                run_lite_env_char_visual_chain(
                    environments_text=environments_text,
                    image_model=model_id,
                    simple_mode=simple_mode_on,
                )
            )
        except Exception as exc:  # noqa: BLE001
            empty_err["error"] = str(exc)
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                empty_err,
            )

        bases_bundle = lite_make_bases_bundle(
            env_results=env_results,
            char_results=char_results,
            url_by_env=url_by_env,
            url_by_char=url_by_char,
            env_order=env_order,
            char_order=char_order,
            simple_mode=simple_mode_on,
        )
        selected = selected_model_id
        prev_blob = (frames_prev_link_raw or "").strip() or None

        try:
            frame_results = run_lite_frame_visual_chain(
                frames_text=(frames_text or "").strip(),
                url_by_env=url_by_env,
                url_by_char=url_by_char,
                env_order=env_order,
                char_order=char_order,
                image_model=model_id,
                frames_prev_link_raw=prev_blob,
                simple_mode=simple_mode_on,
            )
        except Exception as exc:  # noqa: BLE001
            empty_err["error"] = f"Кадры (цепочка): {exc}"
            empty_err["env_results"] = env_results
            empty_err["char_results"] = char_results
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                empty_err,
            )

        await _dream_lite_materialize_playground_frames(
            list(frame_results), dream_lite_artifact_repo
        )
        frames_for_step4_json = lite_frames_metadata_for_montage_form(list(frame_results))
        generation_run_id = uuid.uuid4().hex[:12]
        if dream_lite_step3_snapshot_repo is not None:
            snap_payload = _step3_snapshot_payload(
                dream_text=dream_text,
                environments_text=environments_text,
                frames_text=frames_text,
                frames_prev_link_raw=prev_blob or "",
                bases_bundle_json=json.dumps(bases_bundle, ensure_ascii=False),
                frames_for_step4_json=frames_for_step4_json,
                selected_image_model=selected,
                simple_mode=simple_mode_on,
            )
            await asyncio.to_thread(
                dream_lite_step3_snapshot_repo.upsert_latest_sync,
                user_id=int(settings.dream_lite_playground_user_id),
                payload=snap_payload,
                updated_by="dev_step3_generate_visuals_bases",
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_generate_visual_result.html",
            {
                "error": None,
                "step3_phase": "complete",
                "env_results": env_results,
                "char_results": char_results,
                "frame_results": frame_results,
                "frame_plans": None,
                "bases_bundle_json": json.dumps(bases_bundle, ensure_ascii=False),
                "simple_mode": simple_mode_on,
                "image_models_catalog": _dream_lite_catalog_with_test_stats(),
                "selected_image_model": selected,
                "frames_for_step4_json": frames_for_step4_json,
                "generation_run_id": generation_run_id,
                "dream_lite_playground_user_id": int(settings.dream_lite_playground_user_id),
            },
        )

    @router.post("/api/dream/lite/generate_visuals_frames", response_class=HTMLResponse)
    async def api_dream_lite_generate_visuals_frames(
        request: Request,
        dream_text: str = Form(""),
        frames_text: str = Form(""),
        frames_prev_link_raw: str = Form(""),
        bases_bundle_json: str = Form(""),
        image_model: str = Form(""),
        simple_mode: str = Form(""),
    ) -> Any:
        form_simple_mode = _form_bool(simple_mode)
        base_ctx: dict[str, Any] = {
            "error": None,
            "env_results": [],
            "char_results": [],
            "frame_results": [],
            "frames_for_step4_json": [],
            "step3_phase": "complete",
            "frame_plans": None,
            "bases_bundle_json": (bases_bundle_json or "").strip(),
            "simple_mode": form_simple_mode,
            "image_models_catalog": _dream_lite_catalog_with_test_stats(),
            "selected_image_model": _resolve_step3_image_model(
                image_model,
                simple_mode_on=form_simple_mode,
            ),
            "dream_lite_playground_user_id": int(settings.dream_lite_playground_user_id),
        }
        if not (frames_text or "").strip():
            base_ctx["error"] = "Нет текста раскадровки."
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                base_ctx,
            )
        raw_b = (bases_bundle_json or "").strip()
        if not raw_b:
            base_ctx["error"] = "Нет данных шага 3a (bundle). Сначала «Окружения и персонажи — картинки»."
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                base_ctx,
            )
        try:
            bundle = lite_read_bases_bundle_from_json(json.loads(raw_b))
        except (json.JSONDecodeError, ValueError) as exc:
            base_ctx["error"] = f"Некорректный bases_bundle JSON: {exc}"
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                base_ctx,
            )
        simple_mode_on = form_simple_mode or bool(bundle.get("simple_mode"))
        base_ctx["simple_mode"] = simple_mode_on
        selected_model_id = _resolve_step3_image_model(
            image_model,
            simple_mode_on=simple_mode_on,
        )
        base_ctx["selected_image_model"] = selected_model_id

        model_id = selected_model_id or None
        await _upsert_active_profile_image_policy(
            image_model=model_id,
            simple_mode=simple_mode_on,
        )
        prev_blob = (frames_prev_link_raw or "").strip() or None
        try:
            frame_results = run_lite_frame_visual_chain(
                frames_text=(frames_text or "").strip(),
                url_by_env=bundle["url_by_env"],
                url_by_char=bundle["url_by_char"],
                env_order=bundle["env_order"],
                char_order=bundle["char_order"],
                image_model=model_id,
                frames_prev_link_raw=prev_blob,
                simple_mode=simple_mode_on,
            )
        except Exception as exc:  # noqa: BLE001
            base_ctx["error"] = str(exc)
            base_ctx["env_results"] = list(bundle.get("env_results") or [])
            base_ctx["char_results"] = list(bundle.get("char_results") or [])
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                base_ctx,
            )

        await _dream_lite_materialize_playground_frames(
            list(frame_results), dream_lite_artifact_repo
        )
        frames_for_step4_json = lite_frames_metadata_for_montage_form(list(frame_results))
        generation_run_id = uuid.uuid4().hex[:12]
        if dream_lite_step3_snapshot_repo is not None:
            prev_snap = _load_step3_snapshot_sync() or {}
            snap_payload = _step3_snapshot_payload(
                dream_text=dream_text,
                environments_text=str(prev_snap.get("environments_text") or ""),
                frames_text=frames_text,
                frames_prev_link_raw=prev_blob or "",
                bases_bundle_json=raw_b,
                frames_for_step4_json=frames_for_step4_json,
                selected_image_model=selected_model_id,
                simple_mode=simple_mode_on,
            )
            await asyncio.to_thread(
                dream_lite_step3_snapshot_repo.upsert_latest_sync,
                user_id=int(settings.dream_lite_playground_user_id),
                payload=snap_payload,
                updated_by="dev_step3_generate_visuals_frames",
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_generate_visual_result.html",
            {
                "error": None,
                "step3_phase": "complete",
                "env_results": list(bundle.get("env_results") or []),
                "char_results": list(bundle.get("char_results") or []),
                "frame_results": frame_results,
                "frame_plans": None,
                "bases_bundle_json": raw_b,
                "simple_mode": simple_mode_on,
                "image_models_catalog": _dream_lite_catalog_with_test_stats(),
                "selected_image_model": selected_model_id,
                "frames_for_step4_json": frames_for_step4_json,
                "generation_run_id": generation_run_id,
                "dream_lite_playground_user_id": int(settings.dream_lite_playground_user_id),
            },
        )

    @router.post("/api/dream/lite/generate_visuals", response_class=HTMLResponse)
    async def api_dream_lite_generate_visuals(
        request: Request,
        dream_text: str = Form(""),
        environments_text: str = Form(""),
        frames_text: str = Form(""),
        frames_prev_link_raw: str = Form(""),
        image_model: str = Form(""),
        simple_mode: str = Form(""),
    ) -> Any:
        simple_mode_on = _form_bool(simple_mode)
        selected_model_id = _resolve_step3_image_model(
            image_model,
            simple_mode_on=simple_mode_on,
        )
        if not (environments_text or "").strip():
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                {
                    "error": "Нет текста шага 1 (окружения и персонажи). Сначала выполните шаг 1.",
                    "env_results": [],
                    "char_results": [],
                    "frame_results": [],
                    "frames_for_step4_json": [],
                    "selected_image_model": selected_model_id,
                    **_dream_lite_visual_common_ctx(),
                    "simple_mode": simple_mode_on,
                },
            )
        if not (frames_text or "").strip():
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                {
                    "error": "Нет текста раскадровки. Сначала выполните шаг 2.",
                    "env_results": [],
                    "char_results": [],
                    "frame_results": [],
                    "frames_for_step4_json": [],
                    "selected_image_model": selected_model_id,
                    **_dream_lite_visual_common_ctx(),
                    "simple_mode": simple_mode_on,
                },
            )
        model_id = selected_model_id or None
        await _upsert_active_profile_image_policy(
            image_model=model_id,
            simple_mode=simple_mode_on,
        )
        prev_blob = (frames_prev_link_raw or "").strip() or None
        try:
            payload = run_lite_visual_generation_chain(
                environments_text=environments_text,
                frames_text=frames_text,
                dream_text=dream_text,
                image_model=model_id,
                frames_prev_link_raw=prev_blob,
                simple_mode=simple_mode_on,
            )
        except Exception as exc:  # noqa: BLE001
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_generate_visual_result.html",
                {
                    "error": str(exc),
                    "env_results": [],
                    "char_results": [],
                    "frame_results": [],
                    "frames_for_step4_json": [],
                    "selected_image_model": selected_model_id,
                    "dream_lite_playground_user_id": int(settings.dream_lite_playground_user_id),
                    **_dream_lite_visual_common_ctx(),
                    "simple_mode": simple_mode_on,
                },
            )

        fr = list(payload.get("frame_results") or [])
        await _dream_lite_materialize_playground_frames(fr, dream_lite_artifact_repo)
        payload["frame_results"] = fr
        frames_for_step4_json = lite_frames_metadata_for_montage_form(fr)
        selected = selected_model_id
        generation_run_id = uuid.uuid4().hex[:12]
        step3_bases_bundle_json = json.dumps(
            lite_make_bases_bundle(
                env_results=list(payload.get("env_results") or []),
                char_results=list(payload.get("char_results") or []),
                url_by_env={
                    str(x.get("title") or ""): str((x.get("urls") or [""])[0] or "")
                    for x in list(payload.get("env_results") or [])
                    if isinstance(x, dict) and str(x.get("title") or "").strip()
                },
                url_by_char={
                    str(x.get("title") or ""): str((x.get("urls") or [""])[0] or "")
                    for x in list(payload.get("char_results") or [])
                    if isinstance(x, dict) and str(x.get("title") or "").strip()
                },
                env_order=[str(x.get("title") or "").strip() for x in list(payload.get("env_results") or []) if isinstance(x, dict)],
                char_order=[str(x.get("title") or "").strip() for x in list(payload.get("char_results") or []) if isinstance(x, dict)],
                simple_mode=simple_mode_on,
            ),
            ensure_ascii=False,
        )
        if dream_lite_step3_snapshot_repo is not None:
            snap_payload = _step3_snapshot_payload(
                dream_text=dream_text,
                environments_text=environments_text,
                frames_text=frames_text,
                frames_prev_link_raw=prev_blob or "",
                bases_bundle_json=step3_bases_bundle_json,
                frames_for_step4_json=frames_for_step4_json,
                selected_image_model=selected,
                simple_mode=simple_mode_on,
            )
            await asyncio.to_thread(
                dream_lite_step3_snapshot_repo.upsert_latest_sync,
                user_id=int(settings.dream_lite_playground_user_id),
                payload=snap_payload,
                updated_by="dev_step3_generate_visuals_all",
            )

        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_generate_visual_result.html",
            {
                **_dream_lite_visual_common_ctx(),
                "error": None,
                "frames_for_step4_json": frames_for_step4_json,
                "selected_image_model": selected,
                "simple_mode": simple_mode_on,
                "generation_run_id": generation_run_id,
                "dream_lite_playground_user_id": int(settings.dream_lite_playground_user_id),
                **payload,
                "bases_bundle_json": step3_bases_bundle_json,
            },
        )

    @router.post("/api/dream/lite/step3_snapshot_save", response_class=HTMLResponse)
    async def api_dream_lite_step3_snapshot_save(
        dream_text: str = Form(""),
        environments_text: str = Form(""),
        frames_text: str = Form(""),
        frames_prev_link_raw: str = Form(""),
        bases_bundle_json: str = Form(""),
        frame_results_json: str = Form(""),
        image_model: str = Form(""),
        simple_mode: str = Form(""),
    ) -> Any:
        """Принудительное сохранение последнего успешного шага 3 для ускоренного 4/5 (только Dev)."""
        if dream_lite_step3_snapshot_repo is None:
            return HTMLResponse(
                '<p class="dream-lite-secondary">Хранилище snapshot недоступно.</p>',
                status_code=503,
            )
        raw_f = (frame_results_json or "").strip()
        if not raw_f:
            return HTMLResponse(
                '<p class="err" role="alert">Нет JSON кадров. Сначала выполните шаг 3.</p>',
                status_code=400,
            )
        try:
            parsed = json.loads(raw_f)
            if not isinstance(parsed, list):
                raise ValueError("ожидался массив кадров")
            frames_for_step4: list[dict[str, Any]] = parsed
        except (json.JSONDecodeError, ValueError) as exc:
            return HTMLResponse(
                f'<p class="err" role="alert">Некорректный JSON кадров: {html.escape(str(exc))}</p>',
                status_code=400,
            )
        sm = _form_bool(simple_mode)
        mid = _resolve_step3_image_model(image_model, simple_mode_on=sm)
        await _upsert_active_profile_image_policy(
            image_model=mid,
            simple_mode=sm,
        )
        snap_payload = _step3_snapshot_payload(
            dream_text=dream_text,
            environments_text=environments_text,
            frames_text=frames_text,
            frames_prev_link_raw=frames_prev_link_raw,
            bases_bundle_json=(bases_bundle_json or "").strip(),
            frames_for_step4_json=frames_for_step4,
            selected_image_model=mid,
            simple_mode=sm,
        )
        ok = await asyncio.to_thread(
            dream_lite_step3_snapshot_repo.upsert_latest_sync,
            user_id=int(settings.dream_lite_playground_user_id),
            payload=snap_payload,
            updated_by="dev_step3_snapshot_manual",
        )
        if not ok:
            return HTMLResponse(
                '<p class="err" role="alert">Не удалось записать snapshot в Mongo.</p>',
                status_code=500,
            )
        return HTMLResponse(
            '<p class="dream-lite-secondary"><span class="dream-lite-pill dream-lite-pill--ok">Snapshot сохранён</span> '
            "в Mongo — шаги 4/5 подхватят его при пустых полях.</p>"
        )

    @router.post("/api/dream/lite/montage_plan", response_class=HTMLResponse)
    async def api_dream_lite_montage_plan(
        request: Request,
        dream_text: str = Form(""),
        environments_text: str = Form(""),
        frame_results_json: str = Form(""),
        video_model_id: str = Form(""),
        prompt_mode: str = Form("first_last_frame"),
        audio_required: str = Form(""),
        montage_preset: str = Form(""),
    ) -> Any:
        """Шаг 4: только чат плана монтажа по уже сгенерированным кадрам (метаданные из шага 3)."""
        video_catalog = _dream_lite_video_catalog_with_stats()
        active_video = _active_lite_video_policy()
        selected_video_model = str(active_video.get("openrouter_model") or "").strip() or str(active_video.get("i2v_model") or "").strip()
        selected_prompt_mode = str(active_video.get("prompt_mode") or "first_last_frame").strip() or "first_last_frame"
        selected_audio_required = bool(active_video.get("audio_required"))
        form_video_model = (video_model_id or "").strip()
        if form_video_model:
            selected_video_model = form_video_model
        form_prompt_mode = (prompt_mode or "").strip() or selected_prompt_mode
        if form_prompt_mode not in {"first_frame_only", "text_only", "first_last_frame"}:
            form_prompt_mode = "first_last_frame"
        form_audio_required = str(audio_required or "").strip().lower() in {"1", "true", "on", "yes"}
        if not (audio_required or "").strip():
            form_audio_required = selected_audio_required
        if not selected_video_model and video_catalog:
            selected_video_model = str((video_catalog[0] or {}).get("model_id") or "").strip()
        form_montage_preset = (montage_preset or "").strip().lower()
        if form_montage_preset not in {"default", "seedance", "wan_2_6_single_anchor", "kling_v3_reference_motion"}:
            form_montage_preset = ""
        configured_for_resolve = (
            form_montage_preset
            if form_montage_preset
            else str(active_video.get("montage_preset") or "")
        )
        selected_montage_preset = lite_resolve_montage_preset(
            selected_video_model=selected_video_model,
            configured_preset=configured_for_resolve,
        )
        if selected_montage_preset == "wan_2_6_single_anchor":
            selected_video_model = _WAN26_VIDEO_MODEL_ID
        elif selected_montage_preset == "kling_v3_reference_motion":
            selected_video_model = _KLING_V3_STD_MODEL_ID
        selected_prof = get_video_model_profile(selected_video_model) if selected_video_model else None
        plan_audio_required = form_audio_required
        audio_required_clamp_note = ""
        if selected_prof and str(selected_prof.get("audio_mode") or "") == "silent_only" and plan_audio_required:
            plan_audio_required = False
            audio_required_clamp_note = (
                "Модель помечена как silent_only (без нативного звука): для шага 4 опция «Требовать нативный звук» снята, иначе план монтажа блокируется."
            )
        bundle_vp = video_policy_bundle_for_montage_preset(selected_montage_preset)
        effective_prompt_mode, effective_prompt_policy, prompt_mode_locked = _effective_video_prompt_policy(
            prompt_mode=form_prompt_mode,
            montage_preset=selected_montage_preset,
            audio_required=plan_audio_required,
        )
        if selected_prof:
            selected_backend = str(selected_prof.get("backend") or selected_prof.get("provider") or "").strip()
            selected_i2v = selected_video_model if selected_backend != "openrouter" else str(active_video.get("i2v_model") or "wan2.7-i2v")
            selected_or = selected_video_model if selected_backend == "openrouter" else ""
            if selected_montage_preset == "kling_v3_reference_motion":
                selected_backend = "openrouter"
                selected_or = _KLING_V3_STD_MODEL_ID
                selected_i2v = str(active_video.get("i2v_model") or "wan2.7-i2v")
            await _upsert_active_profile_video_policy(
                backend=selected_backend,
                i2v_model=selected_i2v,
                openrouter_model=selected_or,
                prompt_mode=effective_prompt_mode,
                montage_preset=bundle_vp["montage_preset"],
                audio_required=plan_audio_required,
                duration_sec=int(bundle_vp["duration_sec"]),
                resolution=str(bundle_vp["resolution"]),
                scene_segment_stride=int(bundle_vp["scene_segment_stride"]),
                reference_frame_stride=int(bundle_vp["reference_frame_stride"]),
                require_montage_confirm=bool(bundle_vp["require_montage_confirm"]),
            )
            active_video = _active_lite_video_policy()
            selected_montage_preset = str(active_video.get("montage_preset") or selected_montage_preset).strip() or selected_montage_preset
        video_ctx = {
            "video_models_catalog": video_catalog,
            "selected_video_model": selected_video_model,
            "selected_prompt_mode": effective_prompt_mode,
            "requested_prompt_mode": form_prompt_mode,
            "effective_prompt_policy": effective_prompt_policy,
            "prompt_mode_locked": bool(prompt_mode_locked),
            "selected_audio_required": plan_audio_required,
            "requested_audio_required": form_audio_required,
            "audio_required_clamp_note": audio_required_clamp_note,
            "selected_montage_preset": selected_montage_preset,
            "runtime_entrypoint_step4": "lite_compute_transition_plan",
            "runtime_entrypoint_step5": "tool_image_to_video",
            "selected_video_model_insight": _video_model_insight_from_catalog(video_catalog, selected_video_model, last_n=5),
            "active_video_policy": active_video,
            "openrouter_video_models_catalog": openrouter_video_models_catalog(),
            "selected_video_profile": selected_prof or {},
        }
        if selected_prof:
            mm_ok, mm_reason = _validate_video_mode_model(effective_prompt_mode, selected_video_model, audio_required=plan_audio_required)
            video_ctx["mode_model_compatible"] = mm_ok
            video_ctx["mode_model_reason"] = mm_reason
            if not mm_ok:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/dream_pipeline_lite_step4_montage_result.html",
                    {
                        "error": f"Несовместимая связка mode+model: {effective_prompt_mode} + {selected_video_model} ({mm_reason})",
                        "transition_plan": None,
                        "transition_plan_error": None,
                        "animation_markup": None,
                        **video_ctx,
                    },
                )
        if dream_pipeline_service is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step4_montage_result.html",
                {
                    "error": "Dream pipeline service не подключён.",
                    "transition_plan": None,
                    "transition_plan_error": None,
                    "animation_markup": None,
                    **video_ctx,
                },
            )
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step4_montage_result.html",
                {
                    "error": "OpenAI не сконфигурирован.",
                    "transition_plan": None,
                    "transition_plan_error": None,
                    "animation_markup": None,
                    **video_ctx,
                },
            )
        snapshot = _load_step3_snapshot_sync() or {}
        effective_env_text = (environments_text or "").strip() or str(snapshot.get("environments_text") or "").strip()
        effective_frames_json = (frame_results_json or "").strip()
        if not effective_frames_json:
            snap_frames = snapshot.get("frames_for_step4_json")
            if isinstance(snap_frames, list) and snap_frames:
                try:
                    effective_frames_json = json.dumps(snap_frames, ensure_ascii=False)
                except Exception:
                    effective_frames_json = ""
        if not effective_env_text:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step4_montage_result.html",
                {
                    "error": "Нужен текст шага 1 (окружения и персонажи). Snapshot шага 3 не найден или пуст.",
                    "transition_plan": None,
                    "transition_plan_error": None,
                    "animation_markup": None,
                    **video_ctx,
                },
            )
        raw_json = effective_frames_json
        if not raw_json:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step4_montage_result.html",
                {
                    "error": "Нет данных кадров. Сначала выполните шаг 3 (картинки) или сохраните snapshot.",
                    "transition_plan": None,
                    "transition_plan_error": None,
                    "animation_markup": None,
                    **video_ctx,
                },
            )
        try:
            parsed = json.loads(raw_json)
            if not isinstance(parsed, list):
                raise ValueError("ожидался JSON-массив кадров")
            generated_frames = lite_frames_from_montage_form_metadata(parsed)
        except (json.JSONDecodeError, ValueError) as exc:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step4_montage_result.html",
                {
                    "error": f"Некорректный JSON кадров: {exc}",
                    "transition_plan": None,
                    "transition_plan_error": None,
                    "animation_markup": None,
                    **video_ctx,
                },
            )

        env_c, char_c = split_lite_step1_world(effective_env_text)
        llm_input_payload_preview = lite_transitions_user_payload_dict(
            dream_text=(dream_text or "").strip() or str(snapshot.get("dream_text") or "").strip(),
            env_cards=env_c,
            char_cards=char_c,
            generated_frames=generated_frames,
            montage_preset=selected_montage_preset,
        )
        transition_plan = None
        transition_plan_error = None
        try:
            steps_cfg = _active_lite_steps_cfg()
            if selected_montage_preset == "seedance":
                base_prompt = str(steps_cfg.get("transition_plan_seedance_system_prompt") or "").strip()
                if not base_prompt:
                    base_prompt = lite_transitions_seedance_system_prompt()
            elif selected_montage_preset == "wan_2_6_single_anchor":
                base_prompt = str(steps_cfg.get("transition_plan_wan26_system_prompt") or "").strip()
                if not base_prompt:
                    base_prompt = lite_transitions_wan26_system_prompt()
            elif selected_montage_preset == "kling_v3_reference_motion":
                base_prompt = str(steps_cfg.get("transition_plan_kling_reference_system_prompt") or "").strip()
                if not base_prompt:
                    base_prompt = lite_transitions_kling_reference_system_prompt()
            else:
                base_prompt = str(steps_cfg.get("transition_plan_system_prompt") or "").strip()
                if not base_prompt:
                    base_prompt = lite_transitions_system_prompt()
            transition_plan = await lite_compute_transition_plan(
                openai,
                dream_text=(dream_text or "").strip() or str(snapshot.get("dream_text") or "").strip(),
                env_cards=env_c,
                char_cards=char_c,
                generated_frames=generated_frames,
                transition_system_prompt=lite_build_transition_system_prompt(
                    base_prompt=base_prompt,
                    prompt_mode=effective_prompt_mode,
                    audio_required=plan_audio_required,
                    montage_preset=selected_montage_preset,
                )
                or None,
                montage_preset=selected_montage_preset,
            )
            transition_plan = lite_transition_plan_with_selection(
                transition_plan,
                len(generated_frames),
                generated_frames=generated_frames,
            )
        except ValueError as exc:
            transition_plan = lite_dense_animate_fallback_plan(len(generated_frames))
            transition_plan_error = str(exc)
            transition_plan = lite_transition_plan_with_selection(
                transition_plan,
                len(generated_frames),
                source_hint="fallback_from_dense_transitions",
                generated_frames=generated_frames,
            )
        except Exception as exc:  # noqa: BLE001
            transition_plan = lite_dense_animate_fallback_plan(len(generated_frames))
            transition_plan_error = str(exc)
            transition_plan = lite_transition_plan_with_selection(
                transition_plan,
                len(generated_frames),
                source_hint="fallback_from_dense_transitions",
                generated_frames=generated_frames,
            )

        frame_selection = list((transition_plan or {}).get("frame_selection") or [])
        frame_selection_by_index: dict[int, dict[str, Any]] = {}
        for row in frame_selection:
            if not isinstance(row, dict):
                continue
            try:
                ix = int(row.get("frame_index"))
            except (TypeError, ValueError):
                continue
            frame_selection_by_index[ix] = row
        frame_selection_diag = {
            "source": str((transition_plan or {}).get("frame_selection_source") or "unknown"),
            "parse_fallback": bool((transition_plan or {}).get("_parse_fallback")),
            "error": str(transition_plan_error or "").strip(),
        }

        animation_markup = lite_build_prev_line_animation_markup(
            dream_text=(dream_text or "").strip(),
            generated_frames=generated_frames,
            transition_plan=transition_plan,
            prompt_mode=effective_prompt_mode,
            montage_preset=selected_montage_preset,
            audio_required=plan_audio_required,
        )
        animation_markup = lite_sanitize_animation_markup_for_i2v(animation_markup)
        animation_markup = _normalize_markup_provider_duration(
            animation_markup,
            model_id=selected_video_model,
            default_duration=int(active_video.get("duration_sec") or 4),
        )

        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_step4_montage_result.html",
            {
                "error": None,
                "transition_plan": transition_plan,
                "transition_plan_error": transition_plan_error,
                "animation_markup": animation_markup,
                "generated_frames": generated_frames,
                "frame_selection": frame_selection,
                "frame_selection_by_index": frame_selection_by_index,
                "frame_selection_diag": frame_selection_diag,
                "llm_input_payload_preview": llm_input_payload_preview,
                **video_ctx,
            },
        )

    @router.post("/api/dream/lite/image_feedback", response_class=HTMLResponse)
    async def api_dream_lite_image_feedback(
        generation_run_id: str = Form(""),
        model_id: str = Form(""),
        refs_score: str = Form(""),
        image_score: str = Form(""),
        comment: str = Form(""),
        user_id: str = Form(""),
    ) -> Any:
        rid = (generation_run_id or "").strip()
        mid = (model_id or "").strip()
        uid = int(user_id) if (user_id or "").strip().isdigit() else int(settings.dream_lite_playground_user_id)
        try:
            rs = max(1, min(5, int((refs_score or "0").strip() or "0")))
            iscore = max(1, min(5, int((image_score or "0").strip() or "0")))
        except Exception:
            return HTMLResponse('<p class="dream-lite-secondary">Выберите оценки 1..5.</p>', status_code=400)
        coll = _mongo_sync_collection("dream_lite_image_feedback")
        if coll is None:
            return HTMLResponse('<p class="dream-lite-secondary">feedback storage is unavailable</p>', status_code=503)
        now = datetime.now(timezone.utc)
        doc = {
            "user_id": uid,
            "generation_run_id": rid or uuid.uuid4().hex[:12],
            "model_id": mid,
            "refs_score": rs,
            "image_score": iscore,
            "comment": (comment or "").strip()[:2000],
            "created_at": now,
        }
        try:
            coll.insert_one(doc)
            coll.create_index([("user_id", 1), ("generation_run_id", 1), ("created_at", -1)], name="user_run_created")
            coll.create_index([("model_id", 1), ("created_at", -1)], name="model_created")
        except Exception:
            return HTMLResponse('<p class="dream-lite-secondary">Не удалось сохранить feedback.</p>', status_code=500)
        return HTMLResponse('<p class="dream-lite-secondary">Спасибо, feedback сохранён.</p>')

    @router.post("/api/dream/lite/step5_panel", response_class=HTMLResponse)
    async def api_dream_lite_step5_panel(
        request: Request,
        frame_results_json: str = Form(""),
        transition_plan_json: str = Form(""),
        animation_markup_json: str = Form(""),
        step4_video_policy_json: str = Form(""),
    ) -> Any:
        video_catalog = _dream_lite_video_catalog_with_stats()
        active_video = _active_lite_video_policy()
        selected_video_model = str(active_video.get("openrouter_model") or "").strip() or str(active_video.get("i2v_model") or "").strip()
        if not selected_video_model and video_catalog:
            selected_video_model = str((video_catalog[0] or {}).get("model_id") or "").strip()
        raw_anim = (animation_markup_json or "").strip()
        anim_markup: dict[str, Any] | None = None
        if raw_anim:
            try:
                parsed_anim = json.loads(raw_anim)
                if isinstance(parsed_anim, dict):
                    anim_markup = parsed_anim
            except json.JSONDecodeError:
                anim_markup = None
        if isinstance(anim_markup, dict):
            anim_markup = lite_sanitize_animation_markup_for_i2v(anim_markup)
            anim_markup = _normalize_markup_provider_duration(
                anim_markup,
                model_id=selected_video_model,
                default_duration=int(active_video.get("duration_sec") or 4),
            )

        if anim_markup is None:
            raw_frames = (frame_results_json or "").strip()
            if not raw_frames:
                snap = _load_step3_snapshot_sync() or {}
                snap_frames = snap.get("frames_for_step4_json")
                if isinstance(snap_frames, list) and snap_frames:
                    try:
                        raw_frames = json.dumps(snap_frames, ensure_ascii=False)
                    except Exception:
                        raw_frames = ""
            if not raw_frames:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/dream_pipeline_lite_step5_video_result.html",
                    {
                        "error": None,
                        "animation_markup": None,
                        "video_models_catalog": video_catalog,
                        "selected_video_model": selected_video_model if 'selected_video_model' in locals() else "",
                        "selected_prompt_mode": "first_last_frame",
                        "selected_montage_preset": str(_active_lite_video_policy().get("montage_preset") or "default"),
                        "selected_audio_required": bool(_active_lite_video_policy().get("audio_required")),
                        "selected_video_model_insight": {},
                        "active_video_policy": _active_lite_video_policy(),
                        "openrouter_video_models_catalog": openrouter_video_models_catalog(),
                    },
                )
            try:
                fr = json.loads(raw_frames)
                if not isinstance(fr, list):
                    raise ValueError("ожидался JSON-массив кадров")
                generated_frames = lite_frames_from_montage_form_metadata(fr)
            except (json.JSONDecodeError, ValueError) as exc:
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/dream_pipeline_lite_step5_video_result.html",
                    {"error": f"Некорректный frame_results_json: {exc}"},
                )
            tp = {}
            raw_tp = (transition_plan_json or "").strip()
            if raw_tp:
                try:
                    parsed_tp = json.loads(raw_tp)
                    if isinstance(parsed_tp, dict):
                        tp = parsed_tp
                except json.JSONDecodeError:
                    tp = {}
            anim_markup = lite_build_prev_line_animation_markup(
                dream_text="",
                generated_frames=generated_frames,
                transition_plan=tp,
                prompt_mode=str(active_video.get("prompt_mode") or "first_last_frame"),
                montage_preset=str(active_video.get("montage_preset") or "default"),
                audio_required=bool(active_video.get("audio_required")),
            )
            anim_markup = lite_sanitize_animation_markup_for_i2v(anim_markup)
            anim_markup = _normalize_markup_provider_duration(
                anim_markup,
                model_id=selected_video_model,
                default_duration=int(active_video.get("duration_sec") or 4),
            )

        chosen_policy: dict[str, Any] = {}
        raw_policy = (step4_video_policy_json or "").strip()
        if raw_policy:
            try:
                parsed_policy = json.loads(raw_policy)
                if isinstance(parsed_policy, dict):
                    chosen_policy = parsed_policy
            except json.JSONDecodeError:
                chosen_policy = {}
        selected_prompt_mode = str(active_video.get("prompt_mode") or "first_last_frame").strip() or "first_last_frame"
        selected_audio_required = bool(active_video.get("audio_required"))
        selected_montage_preset = str(active_video.get("montage_preset") or "default").strip() or "default"
        if chosen_policy:
            selected_video_model = str(chosen_policy.get("video_model_id") or selected_video_model).strip() or selected_video_model
            spm = str(chosen_policy.get("prompt_mode") or selected_prompt_mode).strip() or selected_prompt_mode
            if spm in {"first_frame_only", "text_only", "first_last_frame"}:
                selected_prompt_mode = spm
            if "audio_required" in chosen_policy:
                selected_audio_required = bool(chosen_policy.get("audio_required"))
            selected_montage_preset = str(
                chosen_policy.get("montage_preset") or selected_montage_preset
            ).strip() or selected_montage_preset
        selected_prompt_mode, effective_prompt_policy, prompt_mode_locked = _effective_video_prompt_policy(
            prompt_mode=selected_prompt_mode,
            montage_preset=selected_montage_preset,
            audio_required=selected_audio_required,
        )
        if selected_montage_preset == "seedance":
            bundle_vp = video_policy_bundle_for_montage_preset("seedance")
            active_video = dict(active_video)
            active_video["duration_sec"] = int(bundle_vp.get("duration_sec") or 7)
            active_video["resolution"] = str(bundle_vp.get("resolution") or "480x480")
        elif selected_montage_preset == "wan_2_6_single_anchor":
            bundle_vp = video_policy_bundle_for_montage_preset("wan_2_6_single_anchor")
            active_video = dict(active_video)
            active_video["duration_sec"] = int(bundle_vp.get("duration_sec") or 5)
            active_video["resolution"] = str(bundle_vp.get("resolution") or "480x480")
        elif selected_montage_preset == "kling_v3_reference_motion":
            bundle_vp = video_policy_bundle_for_montage_preset("kling_v3_reference_motion")
            active_video = dict(active_video)
            active_video["duration_sec"] = int(bundle_vp.get("duration_sec") or 5)
            active_video["resolution"] = str(bundle_vp.get("resolution") or "720x720")
            selected_video_model = _KLING_V3_STD_MODEL_ID
            selected_prompt_mode = "first_frame_only"
            selected_audio_required = False
        if not selected_video_model and video_catalog:
            selected_video_model = str((video_catalog[0] or {}).get("model_id") or "").strip()
        selected_prof = get_video_model_profile(selected_video_model) if selected_video_model else None
        mm_ok, mm_reason = (_validate_video_mode_model(selected_prompt_mode, selected_video_model, audio_required=selected_audio_required) if selected_prof else (False, "video model profile not found"))
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_step5_video_result.html",
            {
                "error": None,
                "animation_markup": anim_markup,
                "video_models_catalog": video_catalog,
                "selected_video_model": selected_video_model,
                "selected_prompt_mode": selected_prompt_mode,
                "effective_prompt_policy": effective_prompt_policy,
                "prompt_mode_locked": bool(prompt_mode_locked),
                "selected_audio_required": selected_audio_required,
                "selected_montage_preset": selected_montage_preset,
                "runtime_entrypoint_step4": "lite_compute_transition_plan",
                "runtime_entrypoint_step5": "tool_image_to_video",
                "selected_video_model_insight": _video_model_insight_from_catalog(video_catalog, selected_video_model, last_n=5),
                "active_video_policy": active_video,
                "openrouter_video_models_catalog": openrouter_video_models_catalog(),
                "selected_video_profile": selected_prof or {},
                "mode_model_compatible": mm_ok,
                "mode_model_reason": mm_reason,
            },
        )

    @router.post("/api/dream/lite/animate_segment", response_class=HTMLResponse)
    async def api_dream_lite_animate_segment(
        request: Request,
        image_url: str = Form(""),
        last_frame_url: str = Form(""),
        reference_image_url: str = Form(""),
        motion_prompt: str = Form(""),
        final_prompt: str = Form(""),
        model_id: str = Form(""),
        prompt_mode: str = Form("first_last_frame"),
        duration: str = Form("4"),
        resolution: str = Form("720p"),
    ) -> Any:
        """Один сегмент i2v (стартовый кадр + конечный кадр + промпт). Playground: owner lite_playground_0."""
        u0 = (image_url or "").strip()
        u1 = (last_frame_url or "").strip()
        ref_u = (reference_image_url or "").strip()
        mp_raw = (final_prompt or "").strip() or (motion_prompt or "").strip() or "Плавное движение между кадрами."
        mp = lite_sanitize_i2v_text_prompt(mp_raw)
        active_video = _active_lite_video_policy()
        locked = _is_seedance_audio_locked(active_video) or _is_kling_reference_preset(active_video)
        pm = (prompt_mode or "").strip() or "first_last_frame"
        if locked:
            pm = str(active_video.get("prompt_mode") or pm).strip() or pm
        pm, effective_policy, prompt_mode_locked = _effective_video_prompt_policy(
            prompt_mode=pm,
            montage_preset=str(active_video.get("montage_preset") or "default"),
            audio_required=bool(active_video.get("audio_required")),
        )
        active_montage = str(active_video.get("montage_preset") or "default").strip().lower() or "default"
        if active_montage == "kling_v3_reference_motion":
            pm = "first_frame_only"
            effective_policy = "locked_kling_reference_motion"
            prompt_mode_locked = True
            if ref_u:
                u0 = ref_u
        needs_last = pm == "first_last_frame"
        needs_first = pm != "text_only"
        if (needs_first and not u0) or (needs_last and not u1):
            return HTMLResponse(
                '<p class="err dream-lite-visual-err" role="alert">Нужен стартовый кадр; для режима first_last_frame нужен и конечный. Для text_only кадры не требуются.</p>',
                status_code=400,
            )
        r0 = _resolve_i2v_payload_url(u0) if needs_first else ""
        r1 = _resolve_i2v_payload_url(u1)
        if needs_first and not r0:
            return HTMLResponse(
                '<p class="err dream-lite-visual-err" role="alert">Стартовый кадр недоступен для внешнего i2v: нужен публичный URL (PUBLIC_BASE_URL) или актуальный локальный файл.</p>',
                status_code=400,
            )
        if needs_last and not r1:
            return HTMLResponse(
                '<p class="err dream-lite-visual-err" role="alert">Конечный кадр недоступен для внешнего i2v: нужен публичный URL (PUBLIC_BASE_URL) или актуальный локальный файл.</p>',
                status_code=400,
            )
        vp = _active_lite_video_policy()
        selected_model = (model_id or "").strip()
        if locked:
            selected_model = (
                str(active_video.get("openrouter_model") or "").strip()
                or str(active_video.get("i2v_model") or "").strip()
                or selected_model
            )
        prof = get_video_model_profile(selected_model) if selected_model else None
        if selected_model:
            ok_mm, reason_mm = _validate_video_mode_model(pm, selected_model)
            if not ok_mm:
                return HTMLResponse(
                    f'<p class="err dream-lite-visual-err" role="alert">Несовместимая связка mode+model: {html.escape(pm)} + {html.escape(selected_model)} ({html.escape(reason_mm)}).</p>',
                    status_code=400,
                )
        backend = str(vp.get("backend") or "").strip() or str(get_settings().video_generation_backend or "dashscope")
        i2v_model = str(vp.get("i2v_model") or "wan2.7-i2v").strip() or "wan2.7-i2v"
        openrouter_model = str(vp.get("openrouter_model") or "").strip()
        if prof:
            backend = str(prof.get("backend") or backend).strip() or backend
            if backend == "openrouter":
                openrouter_model = str(prof.get("model_id") or openrouter_model).strip()
            else:
                i2v_model = str(prof.get("model_id") or i2v_model).strip()
        effective_model_id = openrouter_model if backend == "openrouter" else i2v_model
        if _is_first_frame_stable_model(effective_model_id):
            pm = "first_frame_only"
            effective_policy = "locked_model_first_frame_only"
            prompt_mode_locked = True
        try:
            dur = int((duration or "4").strip() or "4")
        except Exception:
            dur = int(vp.get("duration_sec") or 4)
        dur = _clamp_i2v_duration_sec(
            dur,
            profile=prof,
            model_id=(openrouter_model if backend == "openrouter" else i2v_model),
            default_value=int(vp.get("duration_sec") or 4),
        )
        res = _normalize_video_resolution_value(
            (resolution or "").strip() or str(vp.get("resolution") or "720p"),
            profile=prof,
        )
        if pm in {"first_frame_only", "text_only"}:
            r1 = None
        if pm == "text_only":
            mp = f"{mp}\n\nMode: text_only (no frame images)."
        try:
            out = tool_image_to_video(
                prompt=mp,
                image_url=r0,
                last_frame_url=r1,
                duration=dur,
                resolution=res,
                owner_user_id=f"lite_playground_{LITE_PLAYGROUND_USER_ID}",
                model=i2v_model,
                video_backend=backend,
                openrouter_model=openrouter_model or None,
                job_extra={
                    "montage_preset": active_montage,
                    "dev_relaxed_validation": True,
                    "reference_image_url": (ref_u or r0 or ""),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return HTMLResponse(
                f'<p class="err dream-lite-visual-err" role="alert">{html.escape(str(exc))}</p>',
                status_code=500,
            )
        if not out.get("ok"):
            return HTMLResponse(
                '<p class="err dream-lite-visual-err" role="alert">'
                f'{html.escape(str(out.get("error") or "ошибка video API"))}</p>',
                status_code=400,
            )
        jid = str(out.get("job_id") or "").strip()
        tracker = f"/dev/partials/video/job_tracker?job_id={html.escape(jid)}"
        launch_label = "video generation" if pm == "text_only" else "i2v"
        return HTMLResponse(
            '<div class="dream-lite-anim-run-result pipe-s0-scene-card">'
            f'<p class="dream-lite-secondary">Запущен {html.escape(launch_label)}. Job: '
            f'<code class="mono">{html.escape(jid)}</code> · policy: <code>{html.escape(effective_policy)}</code>'
            f' · locked=<code>{str(bool(prompt_mode_locked)).lower()}</code></p>'
            f'<p><a href="{tracker}" target="_blank" rel="noopener noreferrer">Статус job (новая вкладка)</a></p>'
            "</div>"
        )

    @router.post("/api/dream/lite/animate_segments_batch", response_class=HTMLResponse)
    async def api_dream_lite_animate_segments_batch(
        animation_markup_json: str = Form(""),
        model_id: str = Form(""),
        prompt_mode: str = Form("first_last_frame"),
        duration: str = Form("4"),
        resolution: str = Form("720p"),
    ) -> Any:
        raw = (animation_markup_json or "").strip()
        if not raw:
            return HTMLResponse('<p class="err dream-lite-visual-err" role="alert">Нет animation_markup_json.</p>', status_code=400)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return HTMLResponse(
                f'<p class="err dream-lite-visual-err" role="alert">Некорректный animation_markup_json: {html.escape(str(exc))}</p>',
                status_code=400,
            )
        if not isinstance(parsed, dict):
            return HTMLResponse('<p class="err dream-lite-visual-err" role="alert">animation_markup_json должен быть объектом.</p>', status_code=400)
        segments: list[dict[str, Any]] = []
        for line in list(parsed.get("lines") or []):
            if not isinstance(line, dict):
                continue
            for seg in list(line.get("segments") or []):
                if isinstance(seg, dict):
                    segments.append(seg)
        if not segments:
            return HTMLResponse('<p class="dream-lite-secondary">Нет сцен для batch-запуска.</p>')

        vp = _active_lite_video_policy()
        selected_model = (model_id or "").strip()
        if not selected_model:
            selected_model = (
                str(vp.get("openrouter_model") or "").strip()
                or str(vp.get("i2v_model") or "").strip()
            )
        active_montage = str(vp.get("montage_preset") or "default")
        active_audio_required = bool(vp.get("audio_required"))
        pm_requested = (prompt_mode or "").strip() or "first_last_frame"
        pm_global, effective_policy, prompt_mode_locked = _effective_video_prompt_policy(
            prompt_mode=pm_requested,
            montage_preset=active_montage,
            audio_required=active_audio_required,
        )
        prof = get_video_model_profile(selected_model) if selected_model else None
        if selected_model:
            ok_mm, reason_mm = _validate_video_mode_model(pm_global, selected_model)
            if not ok_mm:
                return HTMLResponse(
                    f'<p class="err dream-lite-visual-err" role="alert">Несовместимая связка mode+model: {html.escape(pm_global)} + {html.escape(selected_model)} ({html.escape(reason_mm)}).</p>',
                    status_code=400,
                )
        backend = str(vp.get("backend") or "").strip() or str(get_settings().video_generation_backend or "dashscope")
        i2v_model = str(vp.get("i2v_model") or "wan2.7-i2v").strip() or "wan2.7-i2v"
        openrouter_model = str(vp.get("openrouter_model") or "").strip()
        if prof:
            backend = str(prof.get("backend") or backend).strip() or backend
            if backend == "openrouter":
                openrouter_model = str(prof.get("model_id") or openrouter_model).strip()
            else:
                i2v_model = str(prof.get("model_id") or i2v_model).strip()
        effective_model_id = openrouter_model if backend == "openrouter" else i2v_model
        if _is_first_frame_stable_model(effective_model_id):
            pm_global = "first_frame_only"
            effective_policy = "locked_model_first_frame_only"
            prompt_mode_locked = True
        try:
            dur_default = int((duration or "4").strip() or "4")
        except Exception:
            dur_default = int(vp.get("duration_sec") or 4)
        dur_default = _clamp_i2v_duration_sec(
            dur_default,
            profile=prof,
            model_id=(openrouter_model if backend == "openrouter" else i2v_model),
            default_value=int(vp.get("duration_sec") or 4),
        )
        res_default = _normalize_video_resolution_value(
            (resolution or "").strip() or str(vp.get("resolution") or "720p"),
            profile=prof,
        )

        items_html: list[str] = []
        launched = 0
        failed = 0
        for idx, seg in enumerate(segments):
            payload = seg.get("api_payload_preview") if isinstance(seg.get("api_payload_preview"), dict) else {}
            seg_pm = str(
                seg.get("effective_prompt_mode")
                or seg.get("prompt_mode")
                or payload.get("effective_prompt_mode")
                or payload.get("prompt_mode")
                or pm_global
            ).strip() or pm_global
            seg_pm, _, _ = _effective_video_prompt_policy(
                prompt_mode=seg_pm,
                montage_preset=active_montage,
                audio_required=active_audio_required,
            )
            needs_last = seg_pm == "first_last_frame"
            needs_first = seg_pm != "text_only"
            u0 = str(payload.get("image_url") or seg.get("image_url_start") or "").strip()
            u1 = str(payload.get("last_frame_url") or seg.get("image_url_end") or "").strip()
            ref_u = str(payload.get("reference_image_url") or seg.get("reference_image_url") or "").strip()
            if active_montage == "kling_v3_reference_motion":
                seg_pm = "first_frame_only"
                if ref_u:
                    u0 = ref_u
                needs_last = False
                needs_first = True
            if needs_first and not u0:
                failed += 1
                items_html.append(
                    f"<li>Сегмент {idx + 1}: <span class='dream-lite-pill dream-lite-pill--err'>failed</span> · missing image_url</li>"
                )
                continue
            if needs_last and not u1:
                failed += 1
                items_html.append(
                    f"<li>Сегмент {idx + 1}: <span class='dream-lite-pill dream-lite-pill--err'>failed</span> · missing last_frame_url</li>"
                )
                continue
            prompt_text = (
                str(payload.get("prompt") or "").strip()
                or str(seg.get("final_prompt") or "").strip()
                or str(payload.get("motion_prompt") or "").strip()
                or str(seg.get("motion_prompt_suggested") or "").strip()
                or "Плавное движение между кадрами."
            )
            prompt_text = lite_sanitize_i2v_text_prompt(prompt_text)
            if seg_pm == "text_only":
                prompt_text = f"{prompt_text}\n\nMode: text_only (no frame images)."
                u0 = ""
                u1 = ""
            try:
                seg_duration = int(payload.get("duration_sec") or seg.get("duration_sec") or dur_default)
            except Exception:
                seg_duration = dur_default
            seg_duration = _clamp_i2v_duration_sec(
                seg_duration,
                profile=prof,
                model_id=(openrouter_model if backend == "openrouter" else i2v_model),
                default_value=dur_default,
            )
            try:
                resolved_u0 = _resolve_i2v_payload_url(u0) if needs_first else ""
                resolved_u1 = _resolve_i2v_payload_url(u1) if needs_last else None
                if needs_first and not resolved_u0:
                    failed += 1
                    items_html.append(
                        f"<li>Сегмент {idx + 1}: <span class='dream-lite-pill dream-lite-pill--err'>failed</span> · start frame URL is not externally accessible</li>"
                    )
                    continue
                if needs_last and not resolved_u1:
                    failed += 1
                    items_html.append(
                        f"<li>Сегмент {idx + 1}: <span class='dream-lite-pill dream-lite-pill--err'>failed</span> · last frame URL is not externally accessible</li>"
                    )
                    continue
                out = tool_image_to_video(
                    prompt=prompt_text,
                    image_url=resolved_u0,
                    last_frame_url=resolved_u1,
                    duration=seg_duration,
                    resolution=res_default,
                    owner_user_id=f"lite_playground_{LITE_PLAYGROUND_USER_ID}",
                    model=i2v_model,
                    video_backend=backend,
                    openrouter_model=openrouter_model or None,
                    job_extra={
                        "montage_preset": active_montage,
                        "dev_relaxed_validation": True,
                        "reference_image_url": (ref_u or resolved_u0 or ""),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                items_html.append(
                    f"<li>Сегмент {idx + 1}: <span class='dream-lite-pill dream-lite-pill--err'>failed</span> · {html.escape(str(exc))}</li>"
                )
                continue
            if not out.get("ok"):
                failed += 1
                items_html.append(
                    f"<li>Сегмент {idx + 1}: <span class='dream-lite-pill dream-lite-pill--err'>failed</span> · {html.escape(str(out.get('error') or 'video API error'))}</li>"
                )
                continue
            launched += 1
            job_id = str(out.get("job_id") or "").strip()
            items_html.append(
                f"<li>Сегмент {idx + 1}: <span class='dream-lite-pill dream-lite-pill--ok'>queued</span> · job=<code>{html.escape(job_id)}</code> · duration=<code>{seg_duration}s</code></li>"
            )

        return HTMLResponse(
            "<div class='dream-lite-anim-run-result pipe-s0-scene-card'>"
            f"<p class='dream-lite-secondary'>Batch запуск завершён: queued=<code>{launched}</code>, failed=<code>{failed}</code> · policy=<code>{html.escape(effective_policy)}</code> · locked=<code>{str(bool(prompt_mode_locked)).lower()}</code></p>"
            f"<ul class='dream-lite-transition-list'>{''.join(items_html)}</ul>"
            "</div>"
        )

    @router.post("/api/dream/lite/pipeline_all_steps", response_class=HTMLResponse)
    async def api_dream_lite_pipeline_all_steps(
        request: Request,
        dream_text: str = Form(""),
    ) -> Any:
        dt = (dream_text or "").strip()
        if not dt:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_pipeline_all_result.html",
                {"pipeline_error": "Введите текст сна для полного запуска."},
            )
        if dream_lite_run_repo is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_pipeline_all_result.html",
                {"pipeline_error": "dream_lite_run_repo не подключён."},
                status_code=503,
            )
        if dream_pipeline_service is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_pipeline_all_result.html",
                {"pipeline_error": "Dream pipeline service не подключён."},
                status_code=400,
            )
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_pipeline_all_result.html",
                {"pipeline_error": "OpenAI не сконфигурирован."},
                status_code=400,
            )

        lite_run_id = await dream_lite_run_repo.create_run(user_id=LITE_PLAYGROUND_USER_ID, dream_text=dt)
        out: dict[str, Any] = {}
        max_steps = 8000
        step_count = 0
        for _ in range(max_steps):
            step_count += 1
            out = await process_dream_lite_run_step(
                repo=dream_lite_run_repo,
                openai=openai,
                user_id=LITE_PLAYGROUND_USER_ID,
                lite_run_id=lite_run_id,
            )
            if not out.get("ok") or out.get("done") or out.get("await_montage_confirm"):
                break

        doc = await dream_lite_run_repo.get_run(
            user_id=LITE_PLAYGROUND_USER_ID,
            lite_run_id=lite_run_id,
        ) or {}

        env_results = [
            {"title": str(title), **(slot if isinstance(slot, dict) else {})}
            for title, slot in dict(doc.get("generated_env") or {}).items()
        ]
        char_results = [
            {"title": str(title), **(slot if isinstance(slot, dict) else {})}
            for title, slot in dict(doc.get("generated_char") or {}).items()
        ]
        frame_results = list(doc.get("generated_frames") or [])
        transition_plan = doc.get("transition_plan") or None
        animation_markup = None
        if frame_results:
            run_video_policy = ((doc.get("run_config") or {}).get("video_policy") or {})
            animation_markup = lite_build_prev_line_animation_markup(
                dream_text=str(doc.get("dream_text") or ""),
                generated_frames=frame_results,
                transition_plan=transition_plan,
                prompt_mode=str((run_video_policy.get("prompt_mode") or "first_last_frame")),
                montage_preset=str((run_video_policy.get("montage_preset") or "default")),
                audio_required=bool(run_video_policy.get("audio_required")),
            )

        phase = str(doc.get("step_phase") or out.get("step_phase") or out.get("next_phase") or "")
        run_status = str(doc.get("run_status") or ("completed" if out.get("done") else "active"))
        pipeline_error = None
        if step_count >= max_steps and not out.get("done"):
            pipeline_error = "Полный прогон остановлен защитой от зацикливания (step limit)."
        elif not out.get("ok"):
            pipeline_error = str(out.get("error") or doc.get("last_error") or "pipeline_failed")

        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_pipeline_all_result.html",
            {
                "pipeline_error": pipeline_error,
                "run_status": run_status,
                "step_phase": phase,
                "step_count": step_count,
                "lite_run_id": lite_run_id,
                "user_id": LITE_PLAYGROUND_USER_ID,
                "step1_raw": doc.get("step1_raw"),
                "step1_error": None,
                "step1_env_cards": list(doc.get("env_cards") or []),
                "step1_char_cards": list(doc.get("char_cards") or []),
                "step2_raw": doc.get("step2_raw"),
                "step2_prev_link_raw": doc.get("step2_prev_link_raw"),
                "step2_error": None,
                "step2_cards": list(doc.get("frame_cards") or []),
                "error": None,
                "env_results": env_results,
                "char_results": char_results,
                "frame_results": frame_results,
                "transition_plan": transition_plan,
                "transition_plan_raw": doc.get("transition_plan_raw"),
                "animation_markup": animation_markup,
                "i2v_clips_meta": list(doc.get("generated_anim_clips") or []),
                "failed_transitions": list(doc.get("failed_transitions") or []),
                "final_video_url": doc.get("final_video_url"),
                "final_video_error": doc.get("final_assembly_error"),
            },
        )

    @router.post("/api/dream/lite/frames", response_class=HTMLResponse)
    async def api_dream_lite_frames(
        request: Request,
        dream_text: str = Form(""),
        environments_text: str = Form(""),
    ) -> Any:
        if dream_pipeline_service is None:
            return HTMLResponse(
                '<p class="error">Dream pipeline service не подключён.</p>',
                status_code=400,
            )
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            return HTMLResponse('<p class="error">OpenAI не сконфигурирован.</p>', status_code=400)
        if not (dream_text or "").strip():
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step_frames_result.html",
                {
                    "error": "Введите текст сна.",
                    "cards": [],
                    "raw_text": "",
                    "prev_link_raw": "",
                },
            )
        if not (environments_text or "").strip():
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step_frames_result.html",
                {
                    "error": "Сначала выполните шаг 1 (окружения и персонажи).",
                    "cards": [],
                    "raw_text": "",
                    "prev_link_raw": "",
                },
            )
        try:
            steps_cfg = _active_lite_steps_cfg()
            raw_text, prev_link_raw, cards = await lite_run_step2_frames_with_prev_link(
                openai,
                dream_text=dream_text,
                step1_markdown=(environments_text or "").strip(),
                step2_system_prompt=str(steps_cfg.get("text_step2_system_prompt") or "").strip() or None,
                prev_link_system_prompt=str(steps_cfg.get("text_step2_prev_link_system_prompt") or "").strip() or None,
            )
        except Exception as exc:  # noqa: BLE001
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_lite_step_frames_result.html",
                {
                    "error": str(exc),
                    "cards": [],
                    "raw_text": "",
                    "prev_link_raw": "",
                },
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_pipeline_lite_step_frames_result.html",
            {
                "error": None,
                "cards": cards,
                "raw_text": raw_text,
                "prev_link_raw": prev_link_raw,
                "runtime_entrypoint": LITE_STEP2_RUNTIME_ENTRYPOINT,
            },
        )

    @router.post("/api/dream/lite/run/start")
    async def api_dream_lite_run_start(
        dream_text: str = Form(""),
        user_id: int = Form(0),
    ) -> Any:
        """Создать персистентный run (Telegram: передавайте telegram user id)."""
        if dream_lite_run_repo is None:
            raise HTTPException(status_code=503, detail="dream_lite_run_repo not configured")
        lite_run_id = await dream_lite_run_repo.create_run(
            user_id=int(user_id),
            dream_text=dream_text,
        )
        return JSONResponse(
            {"ok": True, "user_id": int(user_id), "lite_run_id": lite_run_id},
        )

    @router.post("/api/dream/lite/run/step")
    async def api_dream_lite_run_step(
        user_id: int = Form(...),
        lite_run_id: str = Form(...),
    ) -> Any:
        """Один шаг очереди: text_step1 → text_step2 → по одному env/char/frame."""
        if dream_lite_run_repo is None:
            raise HTTPException(status_code=503, detail="dream_lite_run_repo not configured")
        if dream_pipeline_service is None:
            raise HTTPException(status_code=400, detail="Dream pipeline service не подключён")
        openai = getattr(dream_pipeline_service, "_openai", None)
        out = await process_dream_lite_run_step(
            repo=dream_lite_run_repo,
            openai=openai,
            user_id=int(user_id),
            lite_run_id=(lite_run_id or "").strip(),
        )
        status_code = 200 if out.get("ok") else 400
        return JSONResponse(out, status_code=status_code)

    @router.post("/api/dream/lite/run/confirm_montage")
    async def api_dream_lite_run_confirm_montage(
        user_id: int = Form(...),
        lite_run_id: str = Form(...),
    ) -> Any:
        """После montage_confirm — перевести run в anim_i2v (Dev и тесты)."""
        if dream_lite_run_repo is None:
            raise HTTPException(status_code=503, detail="dream_lite_run_repo not configured")
        rid = (lite_run_id or "").strip()
        doc = await dream_lite_run_repo.get_run(user_id=int(user_id), lite_run_id=rid)
        if not doc:
            raise HTTPException(status_code=404, detail="run not found")
        if str(doc.get("step_phase") or "") != "montage_confirm":
            raise HTTPException(
                status_code=400,
                detail=f"expected step_phase=montage_confirm, got {doc.get('step_phase')!r}",
            )
        await dream_lite_run_repo.update_run(
            user_id=int(user_id),
            lite_run_id=rid,
            patch={
                "step_phase": "anim_i2v",
                "gen_anim_i": 0,
                "anim_run_complete": False,
                "last_error": None,
            },
        )
        return JSONResponse({"ok": True, "lite_run_id": rid, "step_phase": "anim_i2v"})

    @router.get("/api/dream/lite/run/status")
    async def api_dream_lite_run_status(
        user_id: int = Query(...),
        lite_run_id: str = Query(...),
    ) -> Any:
        if dream_lite_run_repo is None:
            raise HTTPException(status_code=503, detail="dream_lite_run_repo not configured")
        doc = await dream_lite_run_repo.get_run(
            user_id=int(user_id),
            lite_run_id=(lite_run_id or "").strip(),
        )
        if not doc:
            raise HTTPException(status_code=404, detail="run not found")
        return JSONResponse(jsonable_encoder({"ok": True, "run": doc}))

    @router.post("/api/dream/stage0a/test", response_class=HTMLResponse)
    async def api_dream_stage0a_test(
        request: Request,
        dream_text: str = Form(""),
        asset_context_json: str = Form("{}"),
    ) -> Any:
        if dream_pipeline_service is None:
            return HTMLResponse('<p class="error">Dream pipeline service не подключён.</p>', status_code=400)
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            return HTMLResponse('<p class="error">OpenAI не сконфигурирован.</p>', status_code=400)

        dt = (dream_text or "").strip()
        if not dt:
            return HTMLResponse('<p class="error">Пустой текст сна для теста 0A.</p>', status_code=400)

        try:
            parsed_ctx = json.loads(asset_context_json or "{}")
            if not isinstance(parsed_ctx, dict):
                parsed_ctx = {}
        except Exception:
            parsed_ctx = {}
        ctx_short = _asset_ctx_short(parsed_ctx)
        ctx_line = json.dumps(ctx_short, ensure_ascii=False)
        user_input = (
            f"Контекст ассетов: {ctx_line}\n\n"
            f"Текст сна:\n{dt}\n\n"
            "Сформируй плотный beat-outline. Верни JSON строго в формате:\n"
            "{\n"
            '  "header_context": {\n'
            '    "summary": "string",\n'
            '    "environment": {"world_summary": "string"},\n'
            '    "entities": [{"env_id": "string", "title": "string", "description": "string"}],\n'
            '    "world_properties": ["string"],\n'
            '    "meta": {"bits_total": 0}\n'
            "  },\n"
            '  "beats": [\n'
            "    {\n"
            '      "beat_index": 1,\n'
            '      "title": "string",\n'
            '      "core_event": "string",\n'
            '      "beat_description": "string",\n'
            '      "event_steps": ["string"],\n'
            '      "actors": ["string"],\n'
            '      "environment_refs": ["env_id"],\n'
            '      "environment_focus": "string",\n'
            '      "main_character_state": "string",\n'
            '      "key_objects_or_entities": ["string"],\n'
            '      "transition_out": "string",\n'
            '      "story_function": "setup|escalation|transition|danger|discovery|climax|resolution"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Каждый beat должен быть плотным scaffold-узлом, а не короткой подписью.\n"
            "Сначала собери общий мир сна в environment_base, затем опиши beats как локальные узлы внутри этого мира.\n"
            "Не добавляй поля camera/motion/overlap/image_strategy/animation_strategy/duration/shot_design."
        )
        system_prompt = _beat_planner_system_prompt()
        model_id = openai.default_model
        temperature = settings.openai_dream_decompose_temperature
        max_tokens = settings.openai_dream_decompose_max_tokens
        seed = settings.openai_dream_decompose_seed
        assembled_prompt = json.dumps(
            [
                {"role": "system", "content": merge_with_global_model_policy(system_prompt)},
                {"role": "user", "content": user_input},
            ],
            ensure_ascii=False,
            indent=2,
        )
        raw_response = await openai.json_completion(
            system=system_prompt,
            user=user_input,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
        )

        parsed_obj: dict[str, Any] = {}
        final_obj: dict[str, Any] = {"header_context": {}, "beats": []}
        parse_error = ""
        mapping_warning = ""
        try:
            parsed_obj = json.loads(raw_response or "{}")
            src_env_base = parsed_obj.get("environment_base") or {}
            environment_entities: list[dict[str, str]] = []
            if isinstance(src_env_base, dict):
                for j, ent in enumerate((src_env_base.get("environment_entities") or [])[:12], start=1):
                    if not isinstance(ent, dict):
                        continue
                    env_id = str(ent.get("env_id") or f"env_{j}")
                    environment_entities.append(
                        {
                            "env_id": env_id,
                            "title": str(ent.get("title") or env_id),
                            "description": str(ent.get("description") or ""),
                        }
                    )
            environment_base = {
                "world_summary": str(src_env_base.get("world_summary") or "") if isinstance(src_env_base, dict) else "",
                "environment_entities": environment_entities,
                "persistent_world_properties": list(src_env_base.get("persistent_world_properties") or [])
                if isinstance(src_env_base, dict)
                else [],
            }
            beats = []
            src_beats_raw = parsed_obj.get("beats")
            src_beats: list[Any] = []
            if isinstance(src_beats_raw, list):
                src_beats = src_beats_raw
            elif isinstance(src_beats_raw, dict):
                maybe_items = src_beats_raw.get("items")
                if isinstance(maybe_items, list):
                    src_beats = maybe_items
                else:
                    src_beats = [v for v in src_beats_raw.values() if isinstance(v, (dict, str))]
            elif isinstance(src_beats_raw, str):
                try:
                    decoded = json.loads(src_beats_raw)
                    if isinstance(decoded, list):
                        src_beats = decoded
                    elif isinstance(decoded, dict):
                        src_beats = [decoded]
                except Exception:
                    src_beats = []
            if isinstance(src_beats, list) and src_beats:
                for i, b in enumerate(src_beats[:8], start=1):
                    if isinstance(b, str):
                        try:
                            b = json.loads(b)
                        except Exception:
                            continue
                    if not isinstance(b, dict):
                        continue
                    event_steps = b.get("event_steps") or []
                    if not isinstance(event_steps, list):
                        event_steps = [str(event_steps)]
                    actors = b.get("actors") or []
                    if not isinstance(actors, list):
                        actors = [str(actors)]
                    env_refs = b.get("environment_refs") or []
                    if not isinstance(env_refs, list):
                        env_refs = [str(env_refs)]
                    key_entities = b.get("key_objects_or_entities") or []
                    if not isinstance(key_entities, list):
                        key_entities = [str(key_entities)]
                    beats.append(
                        {
                            "beat_index": int(b.get("beat_index") or i),
                            "title": str(b.get("title") or f"Beat {i}"),
                            "core_event": str(b.get("core_event") or ""),
                            "beat_description": str(b.get("beat_description") or ""),
                            "event_steps": event_steps,
                            "actors": actors,
                            "environment_refs": env_refs,
                            "environment_focus": str(b.get("environment_focus") or b.get("environment") or ""),
                            "main_character_state": str(b.get("main_character_state") or ""),
                            "key_objects_or_entities": key_entities,
                            "transition_out": str(b.get("transition_out") or ""),
                            "story_function": str(b.get("story_function") or "transition"),
                        }
                    )
            else:
                for i, s in enumerate((parsed_obj.get("scenes") or [])[:8], start=1):
                    if not isinstance(s, dict):
                        continue
                    row = dict(s)
                    row.setdefault("scene_index", i)
                    if not isinstance(row.get("motion"), dict):
                        row["motion"] = {}
                    try:
                        vv = DreamSceneOutline.model_validate(row).model_dump()
                        beats.append(
                            {
                                "beat_index": int(vv.get("scene_index") or i),
                                "title": vv.get("title") or f"Beat {i}",
                                "core_event": vv.get("short_description") or "",
                                "beat_description": vv.get("scene_description") or vv.get("short_description") or "",
                                "event_steps": [],
                                "actors": vv.get("actors") or [],
                                "environment_refs": [],
                                "environment_focus": vv.get("environment_requirement") or "",
                                "main_character_state": "",
                                "key_objects_or_entities": [],
                                "transition_out": "",
                                "story_function": "transition",
                            }
                        )
                    except Exception:
                        continue
            src_header = parsed_obj.get("header_context") or {}
            if not isinstance(src_header, dict):
                src_header = {}
            src_entities = src_header.get("entities") or environment_base.get("environment_entities") or []
            if not isinstance(src_entities, list):
                src_entities = []
            normalized_entities: list[dict[str, str]] = []
            for j, ent in enumerate(src_entities[:12], start=1):
                if not isinstance(ent, dict):
                    continue
                env_id = str(ent.get("env_id") or f"env_{j}")
                normalized_entities.append(
                    {
                        "env_id": env_id,
                        "title": str(ent.get("title") or env_id),
                        "description": str(ent.get("description") or ""),
                    }
                )
            src_meta = src_header.get("meta") or {}
            if not isinstance(src_meta, dict):
                src_meta = {}
            normalized_header_context = {
                "summary": str(src_header.get("summary") or parsed_obj.get("dream_summary") or "")[:500],
                "environment": {
                    "world_summary": str(
                        (src_header.get("environment") or {}).get("world_summary")
                        if isinstance(src_header.get("environment"), dict)
                        else environment_base.get("world_summary") or ""
                    ),
                },
                "entities": normalized_entities,
                "world_properties": list(
                    src_header.get("world_properties")
                    if isinstance(src_header.get("world_properties"), list)
                    else environment_base.get("persistent_world_properties") or []
                ),
                "meta": {
                    **src_meta,
                    "bits_total": int(src_meta.get("bits_total") or len(beats)),
                },
            }
            final_obj = {"header_context": normalized_header_context, "beats": beats}
            parsed_beats_len = len(src_beats)
            if parsed_beats_len > 0 and not beats:
                mapping_warning = (
                    "Диагностика: parsed response содержит beats, "
                    "но финальный mapping вернул пустой beats. Проверьте формат beat-элементов."
                )
        except Exception as exc:  # noqa: BLE001
            parse_error = str(exc)
        append_beat_planner_run(
            {
                "source": "dev_stage0a_beat_planner",
                "mode": "dev",
                "model_id": model_id,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "seed": seed,
                "system_prompt": system_prompt,
                "user_input": user_input,
                "assembled_prompt": assembled_prompt,
                "raw_response": raw_response,
                "parsed_response": parsed_obj if parsed_obj else None,
                "parse_error": parse_error or None,
                "beats_count_final": len(final_obj.get("beats") or []),
            }
        )

        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_stage0_playground_result.html",
            {
                "stage_label": "0A · Beat Planner",
                "prefix": "stage0a",
                "scenarist_scenes": [],
                "system_prompt": system_prompt,
                "model_input": user_input,
                "raw_response": raw_response,
                "parsed_obj": parsed_obj,
                "final_obj": final_obj,
                "parsed_json": json.dumps(parsed_obj, ensure_ascii=False, indent=2) if parsed_obj else "{}",
                "final_json": json.dumps(final_obj, ensure_ascii=False, indent=2),
                "parse_error": parse_error,
                "mapping_warning": mapping_warning,
            },
        )

    @router.get("/api/dream/stage0a/runs/diff", response_class=HTMLResponse)
    async def api_dream_stage0a_runs_diff() -> Any:
        result = diff_last_two_runs()
        if not result.get("ok"):
            return HTMLResponse(
                (
                    "<p class='muted small'>"
                    + html.escape(str(result.get("reason") or "Недостаточно данных для сравнения."))
                    + "</p>"
                    + f"<p class='muted small'>Лог: <code>{html.escape(str(beat_planner_log_path()))}</code></p>"
                )
            )
        run_a = result.get("run_a") or {}
        run_b = result.get("run_b") or {}
        diffs = result.get("diffs") or {}
        return HTMLResponse(
            (
                "<div class='dream-lab-callout dream-lab-callout--planner'>"
                "<div class='dream-lab-callout-title'>Diff двух последних запусков Beat Planner</div>"
                f"<p class='muted small'><strong>run A:</strong> {html.escape(str(run_a.get('run_id') or '—'))} · {html.escape(str(run_a.get('ts') or '—'))}</p>"
                f"<p class='muted small'><strong>run B:</strong> {html.escape(str(run_b.get('run_id') or '—'))} · {html.escape(str(run_b.get('ts') or '—'))}</p>"
                f"<p class='muted small'><strong>model A/B:</strong> {html.escape(str(run_a.get('model_id') or '—'))} / {html.escape(str(run_b.get('model_id') or '—'))}</p>"
                f"<p class='muted small'><strong>temperature A/B:</strong> {html.escape(str(run_a.get('temperature')))} / {html.escape(str(run_b.get('temperature')))}</p>"
                f"<p class='muted small'><strong>max_tokens A/B:</strong> {html.escape(str(run_a.get('max_tokens')))} / {html.escape(str(run_b.get('max_tokens')))}</p>"
                f"<p class='muted small'><strong>seed A/B:</strong> {html.escape(str(run_a.get('seed')))} / {html.escape(str(run_b.get('seed')))}</p>"
                f"<p class='muted small'><strong>log path:</strong> <code>{html.escape(str(beat_planner_log_path()))}</code></p>"
                "</div>"
                "<details class='dream-lab-raw-details'><summary class='dream-lab-raw-summary muted small'>system_prompt diff</summary>"
                f"<pre class='dream-lab-pre dream-lab-pre--tech'>{html.escape(str(diffs.get('system_prompt') or ''))}</pre></details>"
                "<details class='dream-lab-raw-details'><summary class='dream-lab-raw-summary muted small'>user_input diff</summary>"
                f"<pre class='dream-lab-pre dream-lab-pre--tech'>{html.escape(str(diffs.get('user_input') or ''))}</pre></details>"
                "<details class='dream-lab-raw-details'><summary class='dream-lab-raw-summary muted small'>assembled_prompt diff</summary>"
                f"<pre class='dream-lab-pre dream-lab-pre--tech'>{html.escape(str(diffs.get('assembled_prompt') or ''))}</pre></details>"
                "<details class='dream-lab-raw-details'><summary class='dream-lab-raw-summary muted small'>raw_response diff</summary>"
                f"<pre class='dream-lab-pre dream-lab-pre--tech'>{html.escape(str(diffs.get('raw_response') or ''))}</pre></details>"
            )
        )

    @router.post("/api/dream/stage0b/test", response_class=HTMLResponse)
    async def api_dream_stage0b_test(
        request: Request,
        beats_json: str = Form("{}"),
        mode: str = Form("full"),
    ) -> Any:
        if dream_pipeline_service is None:
            return HTMLResponse('<p class="error">Dream pipeline service не подключён.</p>', status_code=400)
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            return HTMLResponse('<p class="error">OpenAI не сконфигурирован.</p>', status_code=400)

        try:
            beats_obj = json.loads(beats_json or "{}")
            if not isinstance(beats_obj, dict):
                beats_obj = {}
        except Exception:
            beats_obj = {}

        incoming_header = beats_obj.get("header_context") or {}
        if not isinstance(incoming_header, dict):
            incoming_header = {}
        legacy_env = beats_obj.get("environment_base") or {}
        if not isinstance(legacy_env, dict):
            legacy_env = {}
        header_context = {
            "summary": str(incoming_header.get("summary") or beats_obj.get("dream_summary") or ""),
            "environment": (
                incoming_header.get("environment")
                if isinstance(incoming_header.get("environment"), dict)
                else {"world_summary": str(legacy_env.get("world_summary") or "")}
            ),
            "entities": (
                incoming_header.get("entities")
                if isinstance(incoming_header.get("entities"), list)
                else list(legacy_env.get("environment_entities") or [])
            ),
            "world_properties": (
                incoming_header.get("world_properties")
                if isinstance(incoming_header.get("world_properties"), list)
                else list(legacy_env.get("persistent_world_properties") or [])
            ),
            "meta": incoming_header.get("meta") if isinstance(incoming_header.get("meta"), dict) else {},
        }
        beats_payload_all = beats_obj.get("beats") or []
        if not isinstance(beats_payload_all, list):
            beats_payload_all = []
        if not isinstance(header_context.get("meta"), dict):
            header_context["meta"] = {}
        header_context["meta"]["bits_total"] = int(header_context["meta"].get("bits_total") or len(beats_payload_all))
        effective_mode = (mode or "full").strip().lower()
        mode_hint = (
            "Режим: Full JSON. Разверни весь массив beats в связный набор сцен по всему сну."
            if effective_mode != "per_beat"
            else "Режим: Per-beat (iterative). Обрабатывай beats последовательно: один вызов на beat с тем же общим контекстом."
        )
        user_input_common = f"Header Context (JSON):\n{json.dumps(header_context, ensure_ascii=False)}\n\n"
        output_contract = (
            "Преобразуй beat-узлы в черновые сцены. Верни JSON строго в формате:\n"
            "{\n"
            '  "header_context": {...},\n'
            '  "scenes": [\n'
            "    {\n"
            '      "scene_index": 1,\n'
            '      "source_beat_index": 1,\n'
            '      "title": "string",\n'
            '      "short_description": "string",\n'
            '      "scene_description": "string",\n'
            '      "actors": ["string"],\n'
            '      "environment": "string",\n'
            '      "mood": "string",\n'
            '      "scene_goal": "string",\n'
            '      "main_character_state": "string",\n'
            '      "key_objects_or_entities": ["string"]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Важно: beat не равен одной сцене. Один beat может содержать несколько сценических фаз и должен раскрываться в нужное количество сцен.\n"
            "Если внутри beat есть смена локального действия, фокуса, напряжения, визуального центра или фазы события — разбивай на отдельные scenes c тем же source_beat_index.\n"
            "header_context не изменяй: не переписывай, не сокращай, не удаляй поля; просто верни его без изменений.\n"
            "Не добавляй motion/camera/overlap/duration/timing/reference/image/animation поля."
        )
        system_prompt = (
            _scenarist_system_prompt()
            + "\n\n[SCENARIST STAGE 0B ADDENDUM]\n"
            + "Beat не равен одной сцене. Один beat может порождать 1..N сцен.\n"
            + "Выделяй отдельные scenes при смене локального действия, фокуса, напряжения, визуального центра или фазы события.\n"
            + "Сохраняй source_beat_index у каждой сцены.\n"
            + "Не добавляй режиссёрские поля: camera/motion/overlap/timing/duration/reference/image/animation."
        )
        parsed_obj: dict[str, Any] = {}
        final_obj: dict[str, Any] = {"header_context": header_context, "scenes": []}
        raw_response = ""
        model_input_text = ""
        parse_error = ""
        mapping_warning = ""
        try:
            rows: list[dict[str, Any]] = []
            raw_parts: list[str] = []

            def _normalize_rows(parsed: dict[str, Any], start_index: int) -> list[dict[str, Any]]:
                out_rows: list[dict[str, Any]] = []
                for i, item in enumerate(parsed.get("scenes") or [], start=0):
                    if not isinstance(item, dict):
                        continue
                    row = dict(item)
                    src_idx = row.get("source_beat_index")
                    if not src_idx:
                        src_idx = (start_index + i)
                    out_rows.append(
                        {
                            "scene_index": int(start_index + i),
                            "source_beat_index": int(src_idx),
                            "title": str(row.get("title") or f"Scene {start_index + i}"),
                            "short_description": str(row.get("short_description") or ""),
                            "scene_description": str(row.get("scene_description") or ""),
                            "actors": list(row.get("actors") or []),
                            "environment": str(row.get("environment") or ""),
                            "mood": str(row.get("mood") or ""),
                            "scene_goal": str(row.get("scene_goal") or ""),
                            "main_character_state": str(row.get("main_character_state") or ""),
                            "key_objects_or_entities": list(row.get("key_objects_or_entities") or []),
                        }
                    )
                return out_rows

            if effective_mode == "per_beat":
                combined_parsed_runs: list[dict[str, Any]] = []
                for b in beats_payload_all:
                    if not isinstance(b, dict):
                        continue
                    beat_payload = [b]
                    user_input = (
                        user_input_common
                        + f"Beat-узлы (JSON):\n{json.dumps(beat_payload, ensure_ascii=False)}\n\n"
                        + f"{mode_hint}\n\n"
                        + output_contract
                    )
                    model_input_text = user_input
                    rr = await openai.json_completion(system=system_prompt, user=user_input)
                    raw_parts.append(rr or "")
                    parsed_run = json.loads(rr or "{}")
                    if isinstance(parsed_run, dict):
                        combined_parsed_runs.append(parsed_run)
                        rows.extend(_normalize_rows(parsed_run, len(rows) + 1))
                parsed_obj = {
                    "header_context": header_context,
                    "mode": "per_beat",
                    "runs": combined_parsed_runs,
                    "scenes": rows,
                }
                raw_response = "\n\n--- per-beat run split ---\n\n".join(raw_parts)
            else:
                user_input = (
                    user_input_common
                    + f"Beat-узлы (JSON):\n{json.dumps(beats_payload_all, ensure_ascii=False)}\n\n"
                    + f"{mode_hint}\n\n"
                    + output_contract
                )
                model_input_text = user_input
                raw_response = await openai.json_completion(system=system_prompt, user=user_input)
                parsed_obj = json.loads(raw_response or "{}")
                if isinstance(parsed_obj, dict):
                    rows = _normalize_rows(parsed_obj, 1)
            final_obj = {"header_context": header_context, "scenes": rows}
            if len(beats_payload_all) > 0 and len(rows) < len(beats_payload_all):
                mapping_warning = (
                    "Диагностика: сцен меньше, чем beats во входе. "
                    "Проверьте, что Сценарист раскрыл все beat-узлы."
                )
        except Exception as exc:  # noqa: BLE001
            parse_error = str(exc)

        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_stage0_playground_result.html",
            {
                "stage_label": "0B · Сценарист",
                "prefix": "stage0b",
                "scenarist_scenes": [],
                "system_prompt": system_prompt,
                "model_input": model_input_text,
                "raw_response": raw_response,
                "parsed_obj": parsed_obj,
                "final_obj": final_obj,
                "parsed_json": json.dumps(parsed_obj, ensure_ascii=False, indent=2) if parsed_obj else "{}",
                "final_json": json.dumps(final_obj, ensure_ascii=False, indent=2),
                "parse_error": parse_error,
                "mapping_warning": mapping_warning,
            },
        )

    @router.post("/api/dream/stage1/test", response_class=HTMLResponse)
    async def api_dream_stage1_test(
        request: Request,
        scenarist_json: str = Form("{}"),
        dream_text: str = Form(""),
        mode: str = Form("full"),
        director_planning: str = Form("v2"),
        director_phase: str = Form("references"),
        references_plan_json: str = Form("{}"),
        asset_context_json: str = Form("{}"),
    ) -> Any:
        if dream_pipeline_service is None:
            return HTMLResponse('<p class="error">Dream pipeline service не подключён.</p>', status_code=400)
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            return HTMLResponse('<p class="error">OpenAI не сконфигурирован.</p>', status_code=400)
        try:
            scenarist_obj = json.loads(scenarist_json or "{}")
            if not isinstance(scenarist_obj, dict):
                scenarist_obj = {}
        except Exception:
            scenarist_obj = {}
        header_context = scenarist_obj.get("header_context") or {}
        if not isinstance(header_context, dict):
            header_context = {}
        scenes_payload = scenarist_obj.get("scenes") or []
        if not isinstance(scenes_payload, list):
            scenes_payload = []
        asset_ctx = parse_asset_context_playground(asset_context_json)
        dream_text_raw = dream_text if isinstance(dream_text, str) else str(dream_text or "")
        dt_block = director_dream_text_user_block(dream_text_raw)
        planning = (director_planning or "v2").strip().lower()
        phase = (director_phase or "references").strip().lower()
        stage_label = "1 · Режиссёр"
        director_phase_label = ""
        parsed_obj: dict[str, Any] = {}
        final_obj: dict[str, Any] = {"header_context": header_context, "final_scenes": []}
        raw_response = ""
        model_input_text = ""
        parse_error = ""
        mapping_warning = ""
        system_prompt = ""

        def _normalize_director_rows_legacy(
            parsed: dict[str, Any], fallback_scene_index: int
        ) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            src_rows = parsed.get("final_scenes")
            if not isinstance(src_rows, list):
                src_rows = parsed.get("visual_prompts") or []

            def _safe_float(x: Any, default: float = 0.0) -> float:
                try:
                    return float(x)
                except (TypeError, ValueError):
                    return default

            for item in src_rows:
                if not isinstance(item, dict):
                    continue
                out.append(
                    {
                        "scene_index": int(item.get("scene_index") or fallback_scene_index),
                        "source_beat_index": item.get("source_beat_index"),
                        "title": str(item.get("title") or ""),
                        "scene_moment": str(item.get("scene_moment") or item.get("visual_prompt") or ""),
                        "actors": list(item.get("actors") or []),
                        "visual_focus": str(item.get("visual_focus") or ""),
                        "what_to_generate": str(item.get("what_to_generate") or ""),
                        "overlap": bool(item.get("overlap") or False),
                        "dependency_scene_index": item.get("dependency_scene_index"),
                        "generation_strategy": str(item.get("generation_strategy") or "new_start"),
                        "motion_intensity": str(item.get("motion_intensity") or "light"),
                        "trim_sec": _safe_float(item.get("trim_sec"), 0.0),
                        "references": list(item.get("references") or []),
                        "reference_source": str(item.get("reference_source") or "none"),
                        "reference_image_url": str(item.get("reference_image_url") or ""),
                        "visual_prompt": str(item.get("visual_prompt") or ""),
                        "image_prompt": str(item.get("image_prompt") or item.get("visual_prompt") or ""),
                        "animation_prompt": str(item.get("animation_prompt") or ""),
                        "reference_type": str(item.get("reference_type") or "none"),
                    }
                )
            return out

        try:
            if planning == "legacy":
                effective_mode = (mode or "full").strip().lower()
                mode_hint = (
                    "Режим: Full JSON. Обрабатывай header_context и весь массив сцен за один проход."
                    if effective_mode != "per_scene"
                    else "Режим: Per-scene. Обрабатывай сцены последовательно по одной, но всегда с тем же header_context."
                )
                output_contract = (
                    "Верни JSON строго в формате:\n"
                    "{\n"
                    '  "header_context": {...},\n'
                    '  "final_scenes": [\n'
                    "    {\n"
                    '      "scene_index": 1,\n'
                    '      "source_beat_index": 1,\n'
                    '      "title": "string",\n'
                    '      "scene_moment": "string",\n'
                    '      "actors": ["string"],\n'
                    '      "visual_focus": "string",\n'
                    '      "what_to_generate": "string",\n'
                    '      "overlap": false,\n'
                    '      "dependency_scene_index": null,\n'
                    '      "generation_strategy": "new_start|continue_from_previous",\n'
                    '      "motion_intensity": "static|light|active",\n'
                    '      "trim_sec": 0.0,\n'
                    '      "references": [{"kind": "character|last_frame|environment", "source": "string", "note": "string"}],\n'
                    '      "reference_source": "user_reference|generated_image|last_frame|none",\n'
                    '      "reference_image_url": "string",\n'
                    '      "visual_prompt": "string",\n'
                    '      "image_prompt": "string",\n'
                    '      "animation_prompt": "string",\n'
                    '      "reference_type": "base_character|selected_character|environment|none"\n'
                    "    }\n"
                    "  ]\n"
                    "}\n"
                    "header_context не изменяй: верни его без изменений.\n"
                    "Каждая final_scene должна быть самодостаточной: опиши конкретный визуальный момент, что видно в кадре и что именно будет сгенерировано.\n"
                    "Правила: overlap=true означает продолжение предыдущей сцены без нового стартового кадра (используй dependency_scene_index).\n"
                    "trim_sec: static=0.0, light=0.2..0.6, active=0.6..1.2 (отрезка инерционного начала)."
                )
                user_input = (
                    f"{dt_block}"
                    f"Header Context (JSON):\n{json.dumps(header_context, ensure_ascii=False)}\n\n"
                    f"Сцены (JSON):\n{json.dumps(scenes_payload, ensure_ascii=False)}\n\n"
                    f"{mode_hint}\n\n"
                    f"{output_contract}"
                )
                system_prompt = _image_prompts_system()
                rows: list[dict[str, Any]] = []
                raw_parts: list[str] = []
                combined_runs: list[dict[str, Any]] = []
                if effective_mode == "per_scene":
                    for idx, scene in enumerate(scenes_payload, start=1):
                        if not isinstance(scene, dict):
                            continue
                        user_input_scene = (
                            f"{dt_block}"
                            f"Header Context (JSON):\n{json.dumps(header_context, ensure_ascii=False)}\n\n"
                            f"Сцена (JSON):\n{json.dumps([scene], ensure_ascii=False)}\n\n"
                            f"{mode_hint}\n\n"
                            f"{output_contract}"
                        )
                        model_input_text = user_input_scene
                        rr = await openai.json_completion(system=system_prompt, user=user_input_scene)
                        raw_parts.append(rr or "")
                        parsed_run = json.loads(rr or "{}")
                        if isinstance(parsed_run, dict):
                            combined_runs.append(parsed_run)
                            rows.extend(_normalize_director_rows_legacy(parsed_run, idx))
                    raw_response = "\n\n--- per-scene run split ---\n\n".join(raw_parts)
                    parsed_obj = {
                        "header_context": header_context,
                        "mode": "per_scene",
                        "runs": combined_runs,
                        "final_scenes": rows,
                    }
                else:
                    model_input_text = user_input
                    raw_response = await openai.json_completion(system=system_prompt, user=user_input)
                    parsed_obj = json.loads(raw_response or "{}")
                    if isinstance(parsed_obj, dict):
                        rows = _normalize_director_rows_legacy(parsed_obj, 1)
                final_obj = {
                    "header_context": header_context,
                    "director_planning": "legacy",
                    "final_scenes": rows,
                    "dream_text": dream_text_raw,
                }
                stage_label = "1 · Режиссёр (legacy · final_scenes)"
                director_phase_label = "legacy"
                if len(scenes_payload) > 0 and len(rows) < len(scenes_payload):
                    mapping_warning = (
                        "Диагностика: финальных сцен меньше, чем сцен во входе. "
                        "Проверьте, что Режиссёр обработал все сцены."
                    )
            elif phase == "full_plan":
                if planning != "v2":
                    parse_error = (
                        "Режим «Сформировать план» (референсы + кадры подряд) доступен только при "
                        "планировании v2. Переключите «Планирование» на v2 · два этапа."
                    )
                else:
                    director_phase_label = "full_plan"
                    stage_label = "1 · Режиссёр · план (референсы → кадры)"
                    parsed_ref: dict[str, Any] = {}
                    parsed_kf: dict[str, Any] = {}
                    raw_ref = ""
                    raw_kf = ""
                    sys_ref = ""
                    sys_kf = ""
                    raw_sys_ref = read_dream_director_references_raw().strip()
                    sys_ref = raw_sys_ref if raw_sys_ref else default_references_system_prompt()
                    user_input_ref = (
                        f"{PLAYGROUND_POLICY}\n\n"
                        f"{dt_block}"
                        f"Asset context (Playground, JSON):\n{json.dumps(asset_ctx, ensure_ascii=False)}\n\n"
                        f"Header Context (JSON):\n{json.dumps(header_context, ensure_ascii=False)}\n\n"
                        f"Сцены сценариста (JSON):\n{json.dumps(scenes_payload, ensure_ascii=False)}\n\n"
                        f"{references_contract_user_block()}"
                    )
                    model_input_text = f"=== Шаг 1/2 · Глобальные референсы ===\n{user_input_ref}"
                    raw_ref = await openai.json_completion(system=sys_ref, user=user_input_ref)
                    parsed_ref = json.loads(raw_ref or "{}")
                    if not isinstance(parsed_ref, dict):
                        parsed_ref = {}
                    gref = normalize_global_references_block(parsed_ref, header_context=header_context)
                    mapping_warning = ""
                    if scenes_payload and not gref.get("items"):
                        mapping_warning = (
                            "Модель вернула пустой список референсов при непустых сценах — "
                            "шаг ключевых кадров всё равно выполнен с пустым планом."
                        )
                    raw_sys_kf = read_dream_director_keyframes_raw().strip()
                    sys_kf = raw_sys_kf if raw_sys_kf else default_keyframes_system_prompt()
                    gref_norm = gref
                    user_input_kf = (
                        f"{PLAYGROUND_POLICY}\n\n"
                        f"{dt_block}"
                        f"Asset context (Playground, JSON):\n{json.dumps(asset_ctx, ensure_ascii=False)}\n\n"
                        f"Global references plan (JSON):\n{json.dumps(gref_norm, ensure_ascii=False)}\n\n"
                        f"Header Context (JSON):\n{json.dumps(header_context, ensure_ascii=False)}\n\n"
                        f"Сцены сценариста (JSON):\n{json.dumps(scenes_payload, ensure_ascii=False)}\n\n"
                        f"{keyframes_contract_user_block()}"
                    )
                    model_input_text = (
                        model_input_text + f"\n\n=== Шаг 2/2 · Ключевые кадры ===\n{user_input_kf}"
                    )
                    raw_kf = await openai.json_completion(system=sys_kf, user=user_input_kf)
                    parsed_kf = json.loads(raw_kf or "{}")
                    if not isinstance(parsed_kf, dict):
                        parsed_kf = {}
                    kf, vp, pg_notes = normalize_key_frames_bundle(
                        parsed_kf,
                        header_context=header_context,
                        global_references=gref_norm,
                    )
                    shim = build_assembler_final_scenes_shim(kf, vp)
                    final_obj = {
                        "header_context": header_context,
                        "director_planning": "v2",
                        "director_phase": "keyframes",
                        "director_pipeline": "full_plan",
                        "playground_policy": PLAYGROUND_POLICY,
                        "asset_context": asset_ctx,
                        "dream_text": dream_text_raw,
                        "global_references": gref_norm,
                        "key_frames": kf,
                        "video_plan": vp,
                        "playground_notes": pg_notes,
                        "final_scenes": shim,
                        "assembler_shim_note": (
                            "Два вызова режиссёра (1A референсы → 1B кадры) выполнены подряд. "
                            "final_scenes — shim для Сборщика; полный JSON ниже — вход сборщика без копирования."
                        ),
                    }
                    parsed_obj = {"step_references": parsed_ref, "step_keyframes": parsed_kf}
                    raw_response = f"--- raw · references ---\n{raw_ref}\n\n--- raw · keyframes ---\n{raw_kf}"
                    system_prompt = f"=== system · references ===\n{sys_ref}\n\n=== system · keyframes ===\n{sys_kf}"
            elif phase == "references":
                director_phase_label = "references"
                stage_label = "1A · Режиссёр · глобальные референсы"
                raw_sys = read_dream_director_references_raw().strip()
                system_prompt = raw_sys if raw_sys else default_references_system_prompt()
                user_input = (
                    f"{PLAYGROUND_POLICY}\n\n"
                    f"{dt_block}"
                    f"Asset context (Playground, JSON):\n{json.dumps(asset_ctx, ensure_ascii=False)}\n\n"
                    f"Header Context (JSON):\n{json.dumps(header_context, ensure_ascii=False)}\n\n"
                    f"Сцены сценариста (JSON):\n{json.dumps(scenes_payload, ensure_ascii=False)}\n\n"
                    f"{references_contract_user_block()}"
                )
                model_input_text = user_input
                raw_response = await openai.json_completion(system=system_prompt, user=user_input)
                parsed_obj = json.loads(raw_response or "{}")
                if not isinstance(parsed_obj, dict):
                    parsed_obj = {}
                gref = normalize_global_references_block(parsed_obj, header_context=header_context)
                final_obj = {
                    "header_context": header_context,
                    "director_planning": "v2",
                    "director_phase": "references",
                    "playground_policy": PLAYGROUND_POLICY,
                    "asset_context": asset_ctx,
                    "dream_text": dream_text_raw,
                    "global_references": gref,
                    "key_frames": None,
                    "video_plan": None,
                    "final_scenes": [],
                    "assembler_shim_note": (
                        "После этапа 1B появится final_scenes (shim) для Сборщика. "
                        "Сейчас только план референсов — генерации нет."
                    ),
                }
                if scenes_payload and not gref.get("items"):
                    mapping_warning = "Модель вернула пустой список референсов при непустых сценах — проверьте ответ."
            else:
                director_phase_label = "keyframes"
                stage_label = "1B · Режиссёр · ключевые кадры"
                raw_sys = read_dream_director_keyframes_raw().strip()
                system_prompt = raw_sys if raw_sys else default_keyframes_system_prompt()
                try:
                    rj = json.loads(references_plan_json or "{}")
                except Exception:
                    rj = {}
                if not isinstance(rj, dict):
                    rj = {}
                gref_src = rj.get("global_references")
                if gref_src is None and "items" in rj:
                    gref_src = rj
                if not isinstance(gref_src, dict):
                    gref_src = {"items": []}
                gref_norm = normalize_global_references_block(
                    {"global_references": gref_src},
                    header_context=header_context,
                )
                user_input = (
                    f"{PLAYGROUND_POLICY}\n\n"
                    f"{dt_block}"
                    f"Asset context (Playground, JSON):\n{json.dumps(asset_ctx, ensure_ascii=False)}\n\n"
                    f"Global references plan (JSON):\n{json.dumps(gref_norm, ensure_ascii=False)}\n\n"
                    f"Header Context (JSON):\n{json.dumps(header_context, ensure_ascii=False)}\n\n"
                    f"Сцены сценариста (JSON):\n{json.dumps(scenes_payload, ensure_ascii=False)}\n\n"
                    f"{keyframes_contract_user_block()}"
                )
                model_input_text = user_input
                raw_response = await openai.json_completion(system=system_prompt, user=user_input)
                parsed_obj = json.loads(raw_response or "{}")
                if not isinstance(parsed_obj, dict):
                    parsed_obj = {}
                kf, vp, pg_notes = normalize_key_frames_bundle(
                    parsed_obj,
                    header_context=header_context,
                    global_references=gref_norm,
                )
                shim = build_assembler_final_scenes_shim(kf, vp)
                final_obj = {
                    "header_context": header_context,
                    "director_planning": "v2",
                    "director_phase": "keyframes",
                    "playground_policy": PLAYGROUND_POLICY,
                    "asset_context": asset_ctx,
                    "dream_text": dream_text_raw,
                    "global_references": gref_norm,
                    "key_frames": kf,
                    "video_plan": vp,
                    "playground_notes": pg_notes,
                    "final_scenes": shim,
                    "assembler_shim_note": (
                        "final_scenes собран автоматически из key_frames для совместимости со Сборщиком."
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            parse_error = str(exc)

        def _playground_json_dumps(obj: Any, *, fallback: str = "{}") -> str:
            try:
                return json.dumps(obj, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return fallback

        references_bundle_for_next = ""
        if (
            isinstance(final_obj, dict)
            and final_obj.get("director_planning") == "v2"
            and final_obj.get("director_phase") == "references"
        ):
            references_bundle_for_next = _playground_json_dumps(
                {"global_references": final_obj.get("global_references")},
                fallback="{}",
            )

        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_stage0_playground_result.html",
            {
                "stage_label": stage_label,
                "prefix": "stage1",
                "director_phase": director_phase_label,
                "director_planning": planning,
                "references_bundle_for_next": references_bundle_for_next,
                "scenarist_scenes": scenes_payload,
                "system_prompt": system_prompt,
                "model_input": model_input_text,
                "raw_response": raw_response,
                "parsed_obj": parsed_obj,
                "final_obj": final_obj,
                "parsed_json": _playground_json_dumps(parsed_obj) if parsed_obj else "{}",
                "final_json": _playground_json_dumps(final_obj),
                "parse_error": parse_error,
                "mapping_warning": mapping_warning,
            },
        )

    @router.post("/api/dream/playground/generate_stills_batch", response_class=HTMLResponse)
    async def api_dream_playground_generate_stills_batch(
        request: Request,
        batch_label: str = Form("references"),
        items_json: str = Form("[]"),
    ) -> Any:
        """Пошаговая генерация стиллов Playground (после явного подтверждения в UI)."""
        try:
            items = json.loads(items_json or "[]")
        except Exception:
            items = []
        if not isinstance(items, list):
            items = []
        results: list[dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            prompt = str(
                it.get("generation_prompt") or it.get("image_prompt") or it.get("prompt") or ""
            ).strip()
            rid = str(it.get("ref_id") or it.get("frame_index") or "").strip()
            label = str(it.get("label") or it.get("short_label") or rid or "item").strip()
            if not prompt:
                results.append(
                    {
                        "id": rid,
                        "label": label,
                        "ok": False,
                        "error": "Пустой промпт",
                        "urls": [],
                    }
                )
                continue
            tool_res = tool_generate_image_openrouter(prompt)
            payload = tool_res.to_dict()
            results.append(
                {
                    "id": rid,
                    "label": label,
                    "kind": str(it.get("kind") or ""),
                    "ok": bool(payload.get("ok")),
                    "error": payload.get("error"),
                    "urls": list(payload.get("image_urls") or []),
                }
            )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_playground_stills_batch_result.html",
            {
                "batch_label": batch_label,
                "results": results,
            },
        )

    @router.post("/api/dream/playground/storyboard_pipeline", response_class=HTMLResponse)
    async def api_dream_playground_storyboard_pipeline(
        request: Request,
        director_json: str = Form("{}"),
    ) -> Any:
        """
        Один проход: глобальные референсы → ключевые кадры с reference_image_urls
        (окружения/рефы из плана + предыдущий кадр, если не new_scene).
        """
        try:
            director = json.loads(director_json or "{}")
        except Exception:
            director = {}
        if not isinstance(director, dict):
            director = {}

        from services.observability.director_storyboard_playground import (
            run_director_storyboard_pipeline,
        )

        payload = run_director_storyboard_pipeline(director)
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_playground_storyboard_result.html",
            payload,
        )

    @router.post("/api/dream/playground/generate_global_ref_still", response_class=HTMLResponse)
    async def api_dream_playground_generate_global_ref_still(
        request: Request,
        item_json: str = Form("{}"),
        visual_idx: str = Form("0"),
    ) -> Any:
        """Один референс Global References: картинка через OpenRouter (Playground)."""
        try:
            it = json.loads(item_json or "{}")
        except Exception:
            it = {}
        if not isinstance(it, dict):
            it = {}
        prompt = str(
            it.get("generation_prompt") or it.get("image_prompt") or it.get("prompt") or ""
        ).strip()
        rid = str(it.get("ref_id") or "").strip() or "ref"
        ok = False
        urls: list[str] = []
        err: str | None = None
        if not prompt:
            err = "Пустой generation_prompt"
        else:
            try:
                tool_res = tool_generate_image_openrouter(prompt)
                payload = tool_res.to_dict()
                ok = bool(payload.get("ok"))
                urls = list(payload.get("image_urls") or [])
                if not ok:
                    err = str(payload.get("error") or "Ошибка генерации")
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
        if ok and urls:
            it = dict(it)
            it["preview_image_url"] = urls[0]
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_global_ref_gen_slot.html",
            {
                "item": it,
                "ok": ok,
                "urls": urls,
                "error": err,
                "visual_idx": (visual_idx or "0").strip() or "0",
            },
        )

    @router.post("/api/dream/assembler/test", response_class=HTMLResponse)
    async def api_dream_assembler_test(
        request: Request,
        director_json: str = Form("{}"),
        assembler_system: str = Form(""),
        human_logic: str = Form(""),
        enabled_tools_json: str = Form("[]"),
    ) -> Any:
        if dream_pipeline_service is None:
            return HTMLResponse(
                '<p class="error">Dream pipeline service не подключён.</p>',
                status_code=400,
            )
        openai = getattr(dream_pipeline_service, "_openai", None)
        if not openai or not openai.configured:
            return HTMLResponse(
                '<p class="error">OpenAI не сконфигурирован.</p>',
                status_code=400,
            )
        try:
            enabled = json.loads(enabled_tools_json or "[]")
        except Exception:
            enabled = []
        if not isinstance(enabled, list):
            enabled = []
        try:
            director_obj = json.loads(director_json or "{}")
        except Exception:
            director_obj = {}
        if not isinstance(director_obj, dict):
            director_obj = {}

        from services.observability.assembler_sandbox_runner import run_assembler_sandbox

        result = await run_assembler_sandbox(
            openai,
            director_obj=director_obj,
            system_prompt=assembler_system,
            human_logic=human_logic,
            enabled_tool_names=[str(x) for x in enabled if str(x).strip()],
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "partials/dream_assembler_sandbox_result.html",
            result,
        )

    if (
        dream_run_repo is not None
        and dream_scene_repo is not None
        and generated_frame_repo is not None
        and scene_video_repo is not None
    ):

        @router.get("/partials/dream/sidebar", response_class=HTMLResponse)
        async def partial_dream_sidebar(request: Request) -> Any:
            runs = await dream_run_repo.list_recent(limit=50)
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_sidebar.html",
                {"runs": runs, "poll_interval_sec": _DEV_POLL_INTERVAL_SEC},
            )

        @router.get("/partials/dream/pipeline", response_class=HTMLResponse)
        async def partial_dream_pipeline(
            request: Request,
            run_id: str = Query(...),
            fragment: str | None = Query(None),
        ) -> Any:
            run = await dream_run_repo.find_by_id(run_id)
            if not run:
                if (fragment or "").strip().lower() == "live":
                    return HTMLResponse(
                        '<p class="muted">Запуск не найден</p>',
                        status_code=404,
                    )
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/dream_pipeline_detail.html",
                    {
                        "error": "Запуск не найден",
                        "run": None,
                        "cards": [],
                        "poll_interval_sec": _DEV_POLL_INTERVAL_SEC,
                    },
                )
            drid = run_id
            scenes = await dream_scene_repo.list_by_dream_run(drid)
            frames = await generated_frame_repo.list_by_dream_run(drid)
            svs = await scene_video_repo.list_by_dream_run(drid)
            by_idx: dict[int, dict[str, Any]] = {}
            for s in scenes:
                idx = int(s.get("scene_index") or 0)
                if idx:
                    by_idx.setdefault(idx, {})["scene"] = s
            for f in frames:
                idx = int(f.get("scene_index") or 0)
                if idx:
                    by_idx.setdefault(idx, {})["frame"] = f
            for v in svs:
                idx = int(v.get("scene_index") or 0)
                if idx:
                    by_idx.setdefault(idx, {})["scene_video"] = v
            order = sorted(by_idx.keys())
            cards = [{"scene_index": i, **by_idx[i]} for i in order]
            live_ctx: dict[str, Any] = {
                "error": None,
                "run": run,
                "cards": cards,
                "poll_interval_sec": _DEV_POLL_INTERVAL_SEC,
                "openai_model": settings.openai_model,
                "openai_model_dream_decompose": settings.openai_model_dream_decompose,
            }
            if (fragment or "").strip().lower() == "live":
                return _TEMPLATES.TemplateResponse(
                    request,
                    "partials/dream_pipeline_poll_body.html",
                    live_ctx,
                )
            return _TEMPLATES.TemplateResponse(
                request,
                "partials/dream_pipeline_detail.html",
                live_ctx,
            )

    return router


def mount_dev_static(app: Any) -> None:
    if _STATIC.is_dir():
        app.mount(
            "/dev/static",
            StaticFiles(directory=str(_STATIC)),
            name="dev_console_static",
        )


def create_legacy_debug_redirect_router(settings: Settings) -> APIRouter:
    """Редирект /dev/debug/* → /dev/* (старая консоль снята)."""

    async def _guard(request: Request) -> None:
        if not settings.dev_debug_ui_enabled:
            raise HTTPException(status_code=404, detail="Dev console disabled")
        if (not settings.dev_debug_ui_allow_remote) and (not _is_localhost(request)):
            raise HTTPException(status_code=403, detail="Dev console only from localhost")
        if not _check_dev_basic_auth(request, settings):
            raise HTTPException(
                status_code=401,
                detail="Dev console auth required",
                headers={"WWW-Authenticate": 'Basic realm="Dream Dev Console"'},
            )

    r = APIRouter(prefix="/dev/debug", dependencies=[Depends(_guard)])

    @r.get("", include_in_schema=False)
    @r.get("/", include_in_schema=False)
    async def redir_root() -> RedirectResponse:
        return RedirectResponse(url="/dev/", status_code=302)

    return r
