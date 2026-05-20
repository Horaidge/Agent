"""
Dev UI: реестр инструментов, агрегаты по MongoDB и лёгкие overrides на диске.

Источники данных:
- статический каталог из `services.tools.openai_definitions` + метаданные;
- `tool_calls`, `video_jobs`;
- `dev_usage_ledger` (опционально) для учёта dev-генераций;
- `observability_events` для таймлайна по trace_id;
- файлы `prompts/*.md` для Policies.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.observability.repository import ObservabilityRepository
from services.llm.system_prompt_loader import (
    get_global_model_policy_path,
    get_system_prompt_path,
    load_system_prompt,
    merge_with_global_model_policy,
)
from services.tools.openai_definitions import OPENAI_TOOLS_CATALOG
from services.tools.openai_definitions import get_tools_for_runtime
from services.tools.tool_dev_specs import get_tool_dev_spec
from storage.chat_repository import ChatStoreRepository
from storage.dev_usage_ledger_repository import DevUsageLedgerRepository
from storage.dream_run_repository import DreamRunRepository
from storage.dream_scene_repository import DreamSceneRepository
from storage.generated_frame_repository import GeneratedFrameRepository
from storage.scene_video_repository import SceneVideoRepository
from storage.story_video_repository import StoryVideoRepository
from storage.video_job_repository import VideoJobRepository


def get_period_bounds(
    period: str,
    *,
    custom_start: str | None = None,
    custom_end: str | None = None,
) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(UTC)
    p = (period or "all").strip().lower()
    if p == "day":
        return now - timedelta(days=1), now
    if p == "week":
        return now - timedelta(days=7), now
    if p == "month":
        return now - timedelta(days=30), now
    if p == "custom":

        def _parse(s: str | None, end: bool = False) -> datetime | None:
            if not s:
                return None
            try:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                if end:
                    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                return dt.replace(hour=0, minute=0, second=0, microsecond=0)
            except Exception:  # noqa: BLE001
                return None

        return _parse(custom_start), _parse(custom_end, end=True)
    return None, None


_TOOLS_ALL_MAX_LOOKBACK_DAYS = 730


def get_tools_period_bounds(
    period: str,
    *,
    custom_start: str | None = None,
    custom_end: str | None = None,
) -> tuple[datetime | None, datetime | None]:
    """
    Границы дат для Tools UI.

    Для period=all без нижней границы полный скан Mongo может занимать секунды/минуты —
    ограничиваем «всё время» последними _TOOLS_ALL_MAX_LOOKBACK_DAYS днями.
    """
    start, end = get_period_bounds(
        period, custom_start=custom_start, custom_end=custom_end
    )
    if start is None and (period or "").strip().lower() == "all":
        start = datetime.now(UTC) - timedelta(days=_TOOLS_ALL_MAX_LOOKBACK_DAYS)
    return start, end


# обратная совместимость внутри модуля
_period_bounds = get_tools_period_bounds


def _overrides_path(data_dir: Path) -> Path:
    return (data_dir / "runtime" / "dev_tool_overrides.json").resolve()


def _policies_extra_path(data_dir: Path) -> Path:
    return (data_dir / "runtime" / "dev_tool_policies_extra.json").resolve()


def load_tool_overrides(data_dir: Path) -> dict[str, Any]:
    path = _overrides_path(data_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_tool_overrides(data_dir: Path, data: dict[str, Any]) -> None:
    path = _overrides_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_DEFAULT_POLICIES_EXTRA: dict[str, Any] = {
    "available_tools_note": "",
    "usage_rules": "",
    "fallback_logic": "",
    "default_language": "ru",
    "call_conditions": "",
}


def load_policies_extra(data_dir: Path) -> dict[str, Any]:
    path = _policies_extra_path(data_dir)
    if not path.is_file():
        return dict(_DEFAULT_POLICIES_EXTRA)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            merged = dict(_DEFAULT_POLICIES_EXTRA)
            merged.update(raw)
            return merged
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return dict(_DEFAULT_POLICIES_EXTRA)


def save_policies_extra(data_dir: Path, data: dict[str, Any]) -> None:
    path = _policies_extra_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _static_tool_catalog() -> list[dict[str, Any]]:
    """Базовый реестр: OpenAI tools + известные async backend-tools."""
    out: list[dict[str, Any]] = []
    for schema in OPENAI_TOOLS_CATALOG:
        fn = (schema.get("function") or {}).get("name") or "unknown"
        desc = (schema.get("function") or {}).get("description") or ""
        if fn == "generate_dream_pipeline":
            tool_kind = "pipeline"
        elif fn == "image_to_video":
            tool_kind = "async_atomic"
        else:
            tool_kind = "atomic"
        is_async = tool_kind in ("async_atomic", "pipeline")
        category = (
            "dream"
            if "dream" in fn
            else ("video" if "video" in fn else ("image" if "image" in fn else "llm"))
        )
        out.append(
            {
                "name": fn,
                "description": desc,
                "category": category,
                "tool_type": "async" if is_async else "sync",
                "type": tool_kind,
                "schema": schema,
            }
        )
    # дедуп по name
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in out:
        n = row["name"]
        if n in seen:
            continue
        seen.add(n)
        deduped.append(row)
    return deduped


def build_registry_rows(
    *,
    data_dir: Path,
    chat_store: ChatStoreRepository,
    period: str = "all",
    custom_start: str | None = None,
    custom_end: str | None = None,
) -> list[dict[str, Any]]:
    start, end = _period_bounds(period, custom_start=custom_start, custom_end=custom_end)
    since = start
    until = end
    stats_list = chat_store.aggregate_tool_stats_global_sync(since=since, until=until)
    stats_by_name = {s["tool_name"]: s for s in stats_list}
    overrides = load_tool_overrides(data_dir)

    rows: list[dict[str, Any]] = []
    for base in _static_tool_catalog():
        name = base["name"]
        ovr = overrides.get(name) if isinstance(overrides.get(name), dict) else {}
        st = stats_by_name.get(name) or {}
        total = int(st.get("total") or 0)
        ok = int(st.get("success") or 0)
        last = st.get("last_used")
        last_iso = last.isoformat() if hasattr(last, "isoformat") else None
        rate = (ok / total) if total else None
        enabled = ovr.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes")
        rows.append(
            {
                **base,
                "description_ui": (ovr.get("description") or base["description"]),
                "enabled": bool(enabled),
                "timeout_sec": ovr.get("timeout_sec"),
                "retry_count": ovr.get("retry_count"),
                "polling_interval_sec": ovr.get("polling_interval_sec"),
                "hint": ovr.get("hint") or "",
                "total_calls": total,
                "success_count": ok,
                "success_rate": rate,
                "last_used": last_iso,
                "dev_detail": get_tool_dev_spec(name),
                "is_pipeline": base.get("type") == "pipeline",
            }
        )

    # image_to_video: статистика из video_jobs (если есть вызовы без chat tool_calls)
    # считаем все джобы за период как «вызовы» инструмента
    return rows


def _map_pipeline_stage(raw: str | None, status: str | None) -> str:
    s = (status or "").strip().lower()
    st = (raw or "").strip().lower()
    if s == "awaiting_character":
        return "waiting_input"
    if st in ("decomposing",):
        return "running"
    if st in ("generating_images",):
        return "generating_images"
    if st in ("animating",):
        return "animating"
    if st in ("assembling",):
        return "assembling"
    if s in ("completed",):
        return "completed"
    if s in ("failed",):
        return "failed"
    if s in ("started",):
        return "running"
    if s in ("awaiting_character",):
        return "waiting_input"
    return "created"


def list_pipeline_jobs(
    *,
    dream_run_repo: DreamRunRepository | None,
    limit: int = 60,
    only_active: bool = False,
) -> list[dict[str, Any]]:
    if dream_run_repo is None:
        return []
    try:
        docs = dream_run_repo.list_recent_sync(limit=limit)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for d in docs:
        run_id = str(d.get("_id") or "")
        status = str(d.get("status") or "created").lower()
        stage = _map_pipeline_stage(d.get("current_stage"), status)
        if only_active and status in ("completed", "failed"):
            continue
        ca = d.get("created_at")
        ua = d.get("updated_at")
        ca_iso = ca.isoformat() if hasattr(ca, "isoformat") else str(ca or "")
        ua_iso = ua.isoformat() if hasattr(ua, "isoformat") else str(ua or "")
        elapsed_ms = None
        try:
            if hasattr(ca, "__class__") and hasattr(ua, "__class__") and ca and ua:
                elapsed_ms = int((ua - ca).total_seconds() * 1000)
        except Exception:
            elapsed_ms = None
        out.append(
            {
                "job_id": run_id,
                "pipeline_name": "generate_dream_pipeline",
                "user_id": d.get("user_id"),
                "trace_id": d.get("trace_id"),
                "status": status,
                "stage": stage,
                "created_at": ca_iso,
                "updated_at": ua_iso,
                "elapsed_ms": elapsed_ms,
                "scene_count": int(d.get("scene_count") or 0),
            }
        )
    return out


def pipeline_definitions() -> list[dict[str, Any]]:
    spec = get_tool_dev_spec("generate_dream_pipeline") or {}
    schema = (spec.get("openai") or {})
    return [
        {
            "name": "generate_dream_pipeline",
            "description": spec.get("module_summary")
            or "Полный workflow визуализации сна (LLM + tools + backend).",
            "type": "pipeline",
            "async": True,
            "input_params": schema.get("parameters") or [],
            "tools_used": [
                "generate_image",
                "image_to_video",
                "video_trim_start",
                "last_frame_as_reference",
            ],
            "entrypoint": {
                "invoker": "dream intent detector / explicit tool call",
                "input_fields": ["dream_text", "telegram_user_id"],
                "creates": "dream_runs job",
                "returns_immediately": {
                    "job_id": "dream_run._id",
                    "run_id": "dream_run._id",
                    "status": "started|awaiting_character",
                },
            },
            "output_contract": {
                "job_id": "string",
                "run_id": "string",
                "status": "created|running|waiting_input|generating_images|animating|assembling|completed|failed",
                "final_video": "url_or_local_path_or_null",
                "error_state": "null_or_error_text",
            },
            "user_context_loaded": [
                "avatar yes/no",
                "images count",
                "environment refs",
                "previous dream assets",
                "base character profile",
            ],
            "llm_stages": [
                "decomposition",
                "image_prompts",
                "animation_prompts",
            ],
            "stage_details": [
                {
                    "id": "decomposition",
                    "executor": "llm",
                    "input": ["dream_text", "user_context"],
                    "output": ["dream_summary", "scene_outlines"],
                    "error_mode": "invalid_json_or_empty_scenes",
                },
                {
                    "id": "image_prompts",
                    "executor": "llm",
                    "input": ["scene_outlines", "dream_summary", "user_context"],
                    "output": ["visual_prompts_by_scene", "reference_type"],
                    "error_mode": "invalid_json_or_missing_prompts",
                },
                {
                    "id": "generate_images",
                    "executor": "tool:generate_image",
                    "input": ["visual_prompt", "style/context"],
                    "output": ["generated_frames"],
                    "error_mode": "provider_error_timeout",
                },
                {
                    "id": "animate",
                    "executor": "tool:image_to_video",
                    "input": ["frame_image", "animation_prompt"],
                    "output": ["scene_videos", "video_jobs"],
                    "error_mode": "provider_failed_or_timeout",
                },
                {
                    "id": "assemble",
                    "executor": "backend",
                    "input": ["scene_videos"],
                    "output": ["final_video_asset"],
                    "error_mode": "ffmpeg_or_io_failure",
                },
            ],
            "execution_stages": [
                "created",
                "running",
                "waiting_input",
                "generating_images",
                "animating",
                "assembling",
                "completed",
                "failed",
            ],
            "visual_chain": [
                "Stage 1: resolve_style",
                "Stage 2: load_user_context",
                "Stage 3: resolve_avatar (main character)",
                "Stage 4: resolve_actors (secondary characters)",
                "Stage 5: LLM -> decomposition + scene_actor_mapping",
                "Stage 6: LLM -> build prompts with style + actors",
                "Stage 7: Tool -> generate_image/edit_image (per scene)",
                "Stage 8: Tool -> image_to_video (per scene)",
                "Stage 8.1: Tool -> video_trim_start (optional, motion ramp-up cleanup)",
                "Stage 8.2: Tool -> last_frame_as_reference (optional, overlap continuity)",
                "Stage 9: Backend -> assemble video",
            ],
            "interaction": {
                "supports_waiting_input": True,
                "example": "awaiting_character -> user appearance -> resume pipeline",
            },
            "waiting_input_rules": {
                "when": "no face/base character data for user",
                "question": "Опиши внешность или отправь 'анон'",
                "resume": "pipeline resumes after next user reply is consumed",
            },
            "storage_objects": [
                "dream_runs",
                "dream_scenes",
                "generated_frames",
                "scene_videos",
                "story_videos",
                "video_jobs",
            ],
            "security_scope": {
                "accepts_only_validated_fields": True,
                "rejects_arbitrary_commands": True,
                "user_scope_only": True,
                "cross_user_read": False,
            },
        }
    ]


def _tool_contract(tool_row: dict[str, Any]) -> dict[str, Any]:
    name = str(tool_row.get("name") or "")
    params = (((tool_row.get("dev_detail") or {}).get("openai") or {}).get("parameters") or [])
    required = [str(p.get("name")) for p in params if p.get("required")]
    optional = [str(p.get("name")) for p in params if not p.get("required")]
    defaults = (tool_row.get("dev_detail") or {}).get("python_defaults") or {}

    provider = "unknown"
    returns = "unknown"
    errors = ["validation_error", "provider_error", "timeout"]
    latency = "sync"
    if name == "generate_image":
        provider = "Qwen Image / DashScope"
        returns = "image_urls[]"
        errors = ["missing_prompt", "dashscope_error", "empty_result", "network_timeout"]
        latency = "sync (provider dependent)"
    elif name == "image_to_video":
        provider = "Wan video provider"
        returns = "job_id + async status via video_jobs"
        errors = ["missing_image_url", "provider_reject", "poll_timeout", "job_failed"]
        latency = "async (queued job)"
    elif name == "video_trim_start":
        provider = "video post-processing (ffmpeg/service)"
        returns = "trimmed_video_url | artifact reference"
        errors = ["missing_video_url", "invalid_trim_range", "ffmpeg_failed"]
        latency = "sync/async (implementation dependent)"
    elif name == "last_frame_as_reference":
        provider = "video frame extractor (ffmpeg/service)"
        returns = "reference_image_url"
        errors = ["missing_video_url", "frame_extract_failed", "decode_error"]
        latency = "sync/async (implementation dependent)"

    return {
        "name": name,
        "type": tool_row.get("type"),
        "async": tool_row.get("tool_type") == "async",
        "description": tool_row.get("description_ui") or "",
        "required_params": required,
        "optional_params": optional,
        "defaults": defaults,
        "provider": provider,
        "returns": returns,
        "errors": errors,
        "latency_behavior": latency,
    }


def pipeline_runtime_overview(dream_run_repo: DreamRunRepository | None) -> dict[str, Any]:
    if dream_run_repo is None:
        return {
            "active_runs": 0,
            "queue": 0,
            "failed_runs": 0,
            "stuck_stage": 0,
            "retries": 0,
        }
    try:
        docs = dream_run_repo.list_recent_sync(limit=300)
    except Exception:
        docs = []
    active = 0
    queue = 0
    failed = 0
    stuck = 0
    retries = 0
    now = datetime.now(UTC)
    for d in docs:
        st = str(d.get("status") or "").lower()
        if st in ("started", "decomposing", "generating_images", "animating", "assembling"):
            active += 1
        if st in ("created", "awaiting_character"):
            queue += 1
        if st == "failed":
            failed += 1
        if st in ("started", "decomposing", "generating_images", "animating", "assembling"):
            ua = d.get("updated_at")
            if hasattr(ua, "__class__"):
                try:
                    if (now - ua).total_seconds() > 1800:
                        stuck += 1
                except Exception:
                    pass
        retries += int(d.get("retry_count") or 0)
    return {
        "active_runs": active,
        "queue": queue,
        "failed_runs": failed,
        "stuck_stage": stuck,
        "retries": retries,
    }


def build_prompt_dynamic_context(
    *,
    atomic_rows: list[dict[str, Any]],
    pipeline_defs: list[dict[str, Any]],
    runtime: dict[str, Any],
) -> dict[str, str]:
    enabled_atomic = [r for r in atomic_rows if bool(r.get("enabled", True))]
    tools_payload = [_tool_contract(r) for r in enabled_atomic]
    pipelines_payload: list[dict[str, Any]] = []
    for p in pipeline_defs:
        pipelines_payload.append(
            {
                "name": p.get("name"),
                "type": "pipeline",
                "async": bool(p.get("async")),
                "entrypoint": p.get("entrypoint"),
                "returns": p.get("output_contract"),
                "user_context_loaded": p.get("user_context_loaded"),
                "stage_details": p.get("stage_details"),
                "storage_objects": p.get("storage_objects"),
                "waiting_input_rules": p.get("waiting_input_rules"),
                "security_scope": p.get("security_scope"),
                "tool_call_graph": "generate_dream_pipeline -> generate_image (per scene) -> image_to_video (per scene) -> assemble",
            }
        )
    payload = {
        "active_tool_names": [t["name"] for t in tools_payload]
        + [p.get("name") for p in pipelines_payload if p.get("name")],
        "tools": tools_payload,
        "pipelines": pipelines_payload,
        "runtime": runtime,
    }
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    md_lines: list[str] = ["## Tools contracts (dynamic)"]
    for t in tools_payload:
        md_lines.append(f"- {t['name']} (type={t['type']}, async={str(t['async']).lower()})")
        md_lines.append(f"  - provider: {t['provider']}")
        md_lines.append(f"  - required_params: {', '.join(t['required_params']) if t['required_params'] else 'none'}")
        md_lines.append(f"  - optional_params: {', '.join(t['optional_params']) if t['optional_params'] else 'none'}")
        md_lines.append(f"  - defaults: {json.dumps(t['defaults'], ensure_ascii=False)}")
        md_lines.append(f"  - returns: {t['returns']}")
        md_lines.append(f"  - errors: {', '.join(t['errors'])}")
        md_lines.append(f"  - latency: {t['latency_behavior']}")
    md_lines.append("")
    md_lines.append("## Pipeline contracts (dynamic)")
    for p in pipelines_payload:
        md_lines.append(f"- {p['name']} (type=pipeline, async={str(p['async']).lower()})")
        md_lines.append(f"  - entrypoint: {json.dumps(p['entrypoint'], ensure_ascii=False)}")
        md_lines.append(f"  - returns: {json.dumps(p['returns'], ensure_ascii=False)}")
        md_lines.append(f"  - user_context_loaded: {', '.join(p['user_context_loaded'] or [])}")
        md_lines.append("  - stage_details:")
        for st in p.get("stage_details") or []:
            md_lines.append(
                f"    - {st.get('id')} [{st.get('executor')}]: in={st.get('input')} out={st.get('output')} errors={st.get('error_mode')}"
            )
        md_lines.append(f"  - waiting_input_rules: {json.dumps(p['waiting_input_rules'], ensure_ascii=False)}")
        md_lines.append(f"  - storage_objects: {', '.join(p['storage_objects'] or [])}")
        md_lines.append(f"  - security_scope: {json.dumps(p['security_scope'], ensure_ascii=False)}")
        md_lines.append(f"  - tool_call_graph: {p['tool_call_graph']}")
    md_lines.append("")
    md_lines.append("## Runtime / observability")
    md_lines.append(f"- active_runs: {runtime.get('active_runs', 0)}")
    md_lines.append(f"- queue: {runtime.get('queue', 0)}")
    md_lines.append(f"- failed_runs: {runtime.get('failed_runs', 0)}")
    md_lines.append(f"- stuck_stage: {runtime.get('stuck_stage', 0)}")
    md_lines.append(f"- retries: {runtime.get('retries', 0)}")
    return {
        "markdown": "\n".join(md_lines),
        "json": json_text,
    }


def pipeline_storage_summary(
    *,
    dream_scene_repo: DreamSceneRepository | None,
    frame_repo: GeneratedFrameRepository | None,
    scene_video_repo: SceneVideoRepository | None,
    story_repo: StoryVideoRepository | None,
) -> dict[str, Any]:
    def _count(repo: Any) -> int:
        if repo is None:
            return 0
        coll = getattr(repo, "_sync", None)
        if coll is None:
            return 0
        try:
            return int(coll.count_documents({}))
        except Exception:
            return 0

    return {
        "scenes": _count(dream_scene_repo),
        "images": _count(frame_repo),
        "videos": _count(scene_video_repo),
        "story_videos": _count(story_repo),
    }


def _dur_ms(start: Any, end: Any) -> int | None:
    try:
        if start and end and hasattr(start, "__class__") and hasattr(end, "__class__"):
            return int((end - start).total_seconds() * 1000)
    except Exception:
        return None
    return None


def pipeline_job_detail(
    *,
    run_id: str | None,
    dream_run_repo: DreamRunRepository | None,
    dream_scene_repo: DreamSceneRepository | None,
    frame_repo: GeneratedFrameRepository | None,
    scene_video_repo: SceneVideoRepository | None,
    story_repo: StoryVideoRepository | None,
    video_job_repo: VideoJobRepository,
) -> dict[str, Any] | None:
    if not run_id or dream_run_repo is None:
        return None
    run = dream_run_repo.find_by_id_sync(run_id)
    if not run:
        return None
    scenes = (
        dream_scene_repo.list_by_dream_run_sync(run_id)
        if dream_scene_repo is not None
        else []
    )
    frames = (
        frame_repo.list_by_dream_run_sync(run_id)
        if frame_repo is not None
        else []
    )
    sv = (
        scene_video_repo.list_by_dream_run_sync(run_id)
        if scene_video_repo is not None
        else []
    )
    story = None
    if story_repo is not None:
        tr = str(run.get("trace_id") or "")
        if tr:
            try:
                story = story_repo._sync.find_one({"trace_id": tr})  # type: ignore[attr-defined]
            except Exception:
                story = None
    stage_progress = run.get("stage_progress") or {}
    stages: list[dict[str, Any]] = []
    for sid, st in stage_progress.items():
        if not isinstance(st, dict):
            continue
        stages.append(
            {
                "id": sid,
                "status": st.get("status"),
                "started_at": st.get("started_at"),
                "ended_at": st.get("ended_at"),
                "duration_ms": _dur_ms(st.get("started_at"), st.get("ended_at")),
                "done": st.get("done"),
                "total": st.get("total"),
                "error": st.get("error"),
            }
        )
    stages.sort(key=lambda x: x.get("id") or "")

    scene_actor_mapping: list[dict[str, Any]] = []
    used_actor_ids: set[str] = set()
    for s in scenes:
        actor_names = list(s.get("actors") or [])
        actor_ids = [str(x) for x in (s.get("actor_ids") or []) if x]
        for aid in actor_ids:
            used_actor_ids.add(aid)
        scene_actor_mapping.append(
            {
                "scene_index": s.get("scene_index"),
                "title": s.get("title") or "",
                "actors": actor_names,
                "actor_ids": actor_ids,
            }
        )
    scene_actor_mapping.sort(key=lambda x: int(x.get("scene_index") or 0))

    child_calls: list[dict[str, Any]] = []
    for f in frames:
        child_calls.append(
            {
                "scene_index": f.get("scene_index"),
                "tool": "generate_image",
                "status": f.get("status") or "generated",
                "started_at": f.get("generation_started_at"),
                "duration_ms": _dur_ms(
                    f.get("generation_started_at"),
                    f.get("generation_completed_at"),
                ),
                "result": (f.get("image_url") or "")[:200],
            }
        )
    by_job_id = {str(v.get("video_job_id") or ""): v for v in sv}
    for jid, row in by_job_id.items():
        if not jid:
            continue
        vj = video_job_repo.get_job_sync(jid)
        child_calls.append(
            {
                "scene_index": row.get("scene_index"),
                "tool": "image_to_video",
                "status": (vj or {}).get("status") or row.get("status") or "queued",
                "started_at": (vj or {}).get("created_at") or row.get("created_at"),
                "duration_ms": _dur_ms(
                    (vj or {}).get("created_at"),
                    (vj or {}).get("updated_at"),
                ),
                "result": ((vj or {}).get("video_url") or row.get("video_url") or "")[:200],
            }
        )
    child_calls.sort(key=lambda x: (int(x.get("scene_index") or 0), x.get("tool") or ""))

    vj_stats = video_job_repo._sync.aggregate(  # type: ignore[attr-defined]
        [
            {"$match": {"dream_run_id": run_id}},
            {"$group": {"_id": "$status", "cnt": {"$sum": 1}}},
        ]
    )
    queue = {"queued": 0, "running": 0, "failed": 0, "waiting_input": 0}
    for s in vj_stats:
        name = str(s.get("_id") or "").lower()
        cnt = int(s.get("cnt") or 0)
        if name in ("created", "queued"):
            queue["queued"] += cnt
        elif name in ("running",):
            queue["running"] += cnt
        elif name in ("failed",):
            queue["failed"] += cnt
    if str(run.get("status") or "").lower() == "awaiting_character":
        queue["waiting_input"] = 1

    return {
        "run": run,
        "stages": stages,
        "child_calls": child_calls,
        "style": run.get("style") or {},
        "actor_bindings": run.get("actor_bindings") or {},
        "scene_actor_mapping": scene_actor_mapping,
        "resolved_actors_count": len(used_actor_ids),
        "current_stage": _map_pipeline_stage(run.get("current_stage"), run.get("status")),
        "elapsed_ms": _dur_ms(run.get("created_at"), run.get("updated_at")),
        "active_tasks": queue["running"],
        "pending_tasks": queue["queued"],
        "queue": queue,
        "user_context": {
            "avatar": bool((run.get("asset_context_snapshot") or {}).get("has_face")),
            "images_count": len(frames),
            "has_base_character": bool(
                (run.get("asset_context_snapshot") or {}).get("has_base_character")
            ),
            "base_character_asset_id": (run.get("asset_context_snapshot") or {}).get("base_character_asset_id"),
            "selected_character_asset_id": (run.get("asset_context_snapshot") or {}).get("selected_character_asset_id"),
            "scope": "user-scoped only",
        },
        "storage": {
            "scenes": len(scenes),
            "images": len(frames),
            "videos": len(sv),
            "final_result": bool(story),
        },
    }


def merge_video_stats_from_aggregate(
    rows: list[dict[str, Any]],
    video_agg: dict[str, Any],
) -> None:
    """Добавляет к строке image_to_video агрегаты video_jobs (без загрузки всех документов)."""
    total = int(video_agg.get("total") or 0)
    ok = int(video_agg.get("succeeded") or 0)
    last_ts = video_agg.get("last_created")
    for r in rows:
        if r.get("name") == "image_to_video":
            prev_t = int(r.get("total_calls") or 0)
            prev_ok = int(r.get("success_count") or 0)
            r["total_calls"] = prev_t + total
            r["success_count"] = prev_ok + ok
            t = r["total_calls"]
            r["success_rate"] = (r["success_count"] / t) if t else None
            lu = r.get("last_used")
            if last_ts and hasattr(last_ts, "isoformat"):
                new_iso = last_ts.isoformat()
                if not lu or new_iso > lu:
                    r["last_used"] = new_iso
            break


def list_unified_executions(
    *,
    chat_store: ChatStoreRepository,
    video_job_repo: VideoJobRepository,
    limit: int = 60,
    period: str = "all",
    custom_start: str | None = None,
    custom_end: str | None = None,
    tool_name: str | None = None,
    status_filter: str | None = None,
    internal_user_id: str | None = None,
    only_errors: bool = False,
    only_active: bool = False,
) -> list[dict[str, Any]]:
    start, end = _period_bounds(period, custom_start=custom_start, custom_end=custom_end)
    since = start
    until = end

    out: list[dict[str, Any]] = []

    if not only_active:
        tcalls = chat_store.list_tool_calls_global_sync(
            limit=limit,
            since=since,
            until=until,
            tool_name=tool_name,
            internal_user_id=internal_user_id,
            only_failed=only_errors,
        )
        for d in tcalls:
            ca = d.get("created_at")
            ca_iso = ca if isinstance(ca, str) else (
                ca.isoformat() if hasattr(ca, "isoformat") else ""
            )
            ok = bool(d.get("success"))
            st = "failed" if not ok else "completed"
            if status_filter and st != status_filter:
                continue
            tid = d.get("trace_id")
            eid = str(d.get("_id") or "")
            out.append(
                {
                    "kind": "tool_call",
                    "id": eid,
                    "detail_href": f"/dev/partials/tools/execution?exec_id={quote(eid, safe='')}",
                    "tool_name": d.get("tool_name"),
                    "user_id": d.get("telegram_user_id"),
                    "internal_user_id": d.get("internal_user_id"),
                    "trace_id": tid,
                    "status": st,
                    "ui_status": st,
                    "started_at": ca_iso,
                    "elapsed_ms": None,
                    "input_summary": _short_json(d.get("tool_args")),
                    "output_summary": _short_json(d.get("tool_result")),
                    "error": (d.get("tool_result") or {}).get("error") if not ok else None,
                    "async_mode": False,
                }
            )

    if only_active:
        jobs = video_job_repo.list_active_sync(limit=limit)
    else:
        jobs = video_job_repo.list_filtered_sync(
            limit=limit,
            since=since,
            until=until,
            owner_user_id=internal_user_id,
        )
    for j in jobs:
        if tool_name and tool_name != "image_to_video":
            continue
        raw_st = (j.get("status") or "").lower()
        ui_st, display = _map_video_job_status(raw_st)
        if status_filter and ui_st != status_filter:
            continue
        if only_errors and ui_st not in ("failed", "timeout"):
            continue
        ca = j.get("created_at")
        ua = j.get("updated_at")
        ca_iso = ca if isinstance(ca, str) else (
            ca.isoformat() if hasattr(ca, "isoformat") else ""
        )
        elapsed = None
        if hasattr(ca, "__class__") and ua and hasattr(ua, "__class__"):
            try:
                if isinstance(ca, str):
                    ca_dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                else:
                    ca_dt = ca
                if isinstance(ua, str):
                    ua_dt = datetime.fromisoformat(ua.replace("Z", "+00:00"))
                else:
                    ua_dt = ua
                elapsed = int((ua_dt - ca_dt).total_seconds() * 1000)
            except Exception:  # noqa: BLE001
                elapsed = None
        vid = f"vj:{j.get('_id')}"
        out.append(
            {
                "kind": "video_job",
                "id": vid,
                "detail_href": f"/dev/partials/tools/execution?exec_id={quote(vid, safe='')}",
                "tool_name": "image_to_video",
                "user_id": _safe_int(j.get("owner_user_id")),
                "internal_user_id": str(j.get("owner_user_id") or ""),
                "trace_id": j.get("dream_trace_id"),
                "status": display,
                "ui_status": ui_st,
                "started_at": ca_iso,
                "elapsed_ms": elapsed,
                "input_summary": (j.get("prompt") or "")[:240],
                "output_summary": (j.get("video_url") or "")[:240],
                "error": j.get("error"),
                "async_mode": True,
                "raw_status": raw_st,
            }
        )

    out.sort(key=lambda x: x.get("started_at") or "", reverse=True)
    return out[:limit]


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _map_video_job_status(raw: str) -> tuple[str, str]:
    raw = (raw or "").lower()
    if raw in ("created",):
        return "queued", "queued"
    if raw in ("running",):
        return "running", "running"
    if raw in ("succeeded",):
        return "completed", "completed"
    if raw in ("failed",):
        return "failed", "failed"
    if raw in ("stale_timeout",):
        return "failed", "stale_timeout"
    return "waiting_provider", raw or "unknown"


def _short_json(obj: Any, n: int = 180) -> str:
    if obj is None:
        return ""
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        s = str(obj)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def get_execution_detail(
    *,
    exec_id: str,
    chat_store: ChatStoreRepository,
    video_job_repo: VideoJobRepository,
) -> dict[str, Any] | None:
    if exec_id.startswith("vj:"):
        jid = exec_id[3:]
        doc = video_job_repo.get_job_sync(jid)
        if not doc:
            return None
        raw_st = (doc.get("status") or "").lower()
        ui_st, _ = _map_video_job_status(raw_st)
        terminal_failed = raw_st in {"failed", "stale_timeout"}
        steps = [
            {"id": "queued", "title": "Queued", "status": "ok" if not terminal_failed else "skip"},
            {"id": "provider", "title": "Sent to provider", "status": "ok" if raw_st in ("running", "succeeded", "failed", "stale_timeout") else "pending"},
            {"id": "poll", "title": "Polling", "status": "ok" if raw_st in ("succeeded", "failed", "stale_timeout") else ("running" if raw_st == "running" else "pending")},
            {"id": "result", "title": "Result", "status": "ok" if raw_st == "succeeded" else ("failed" if terminal_failed else "pending")},
        ]
        return {
            "kind": "video_job",
            "id": exec_id,
            "tool_name": "image_to_video",
            "status": ui_st,
            "trace_id": doc.get("dream_trace_id"),
            "user_id": doc.get("owner_user_id"),
            "started_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "input": doc,
            "output": {"video_url": doc.get("video_url"), "error": doc.get("error")},
            "steps": steps,
        }

    doc = chat_store.get_tool_call_by_id_sync(exec_id)
    if not doc:
        return None
    ok = bool(doc.get("success"))
    st = "failed" if not ok else "completed"
    steps = [
        {"id": "user", "title": "User / Model", "status": "ok"},
        {"id": "tool", "title": f"Tool `{doc.get('tool_name')}`", "status": "ok" if ok else "failed"},
        {"id": "result", "title": "Result", "status": "ok" if ok else "failed"},
    ]
    return {
        "kind": "tool_call",
        "id": doc.get("_id"),
        "tool_name": doc.get("tool_name"),
        "status": st,
        "trace_id": doc.get("trace_id"),
        "user_id": doc.get("telegram_user_id"),
        "started_at": doc.get("created_at"),
        "input": doc.get("tool_args"),
        "output": doc.get("tool_result"),
        "steps": steps,
        "raw_doc": doc,
    }


def trace_timeline(
    trace_id: str | None,
    obs_repo: ObservabilityRepository,
    *,
    limit: int = 120,
) -> list[dict[str, Any]]:
    if not trace_id:
        return []
    events = obs_repo.list_events_sync(trace_id=trace_id, limit=limit)
    out: list[dict[str, Any]] = []
    for ev in events:
        ca = ev.get("created_at")
        ca_iso = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)
        out.append(
            {
                "created_at": ca_iso,
                "event_type": ev.get("event_type"),
                "payload": ev.get("payload"),
            }
        )
    out.reverse()
    return out


def analytics_summary(
    *,
    chat_store: ChatStoreRepository,
    video_job_repo: VideoJobRepository,
    data_dir: Path,
    period: str = "month",
    custom_start: str | None = None,
    custom_end: str | None = None,
    video_agg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start, end = _period_bounds(period, custom_start=custom_start, custom_end=custom_end)
    since = start
    until = end
    stats = chat_store.aggregate_tool_stats_global_sync(since=since, until=until)
    total_calls = sum(int(s.get("total") or 0) for s in stats)
    total_ok = sum(int(s.get("success") or 0) for s in stats)
    failed = total_calls - total_ok
    if video_agg is None:
        try:
            video_agg = video_job_repo.aggregate_period_stats_sync(since=since, until=until)
        except Exception:  # noqa: BLE001
            video_agg = {"total": 0, "succeeded": 0, "failed": 0}
    j_total = int(video_agg.get("total") or 0)
    j_fail = int(video_agg.get("failed") or 0)
    overrides = load_tool_overrides(data_dir)
    catalog = _static_tool_catalog()
    active_tools = sum(
        1
        for c in catalog
        if (overrides.get(c["name"]) or {}).get("enabled", True) is not False
    )
    top = sorted(
        (
            {
                "name": s["tool_name"],
                "calls": int(s.get("total") or 0),
                "failed": int(s.get("total") or 0) - int(s.get("success") or 0),
            }
            for s in stats
        ),
        key=lambda x: x["calls"],
        reverse=True,
    )[:8]
    series = chat_store.tool_calls_timeseries_sync(since=since, until=until, bucket="day")
    return {
        "total_tools": len(catalog),
        "active_tools": active_tools,
        "total_calls": total_calls + j_total,
        "failed_calls": failed + j_fail,
        "avg_latency_ms": None,
        "p95_latency_ms": None,
        "top_tools": top,
        "series": series,
        "tool_stats": stats,
    }


def prompt_file_meta(text: str | None) -> dict[str, Any]:
    """Краткое описание файла промпта для Dev UI (без полного текста в summary)."""
    raw = text if text is not None else ""
    stripped = raw.strip()
    lines = len(raw.splitlines()) if raw else 0
    first_line = ""
    if stripped:
        first_line = stripped.split("\n", 1)[0].strip()
        if len(first_line) > 140:
            first_line = first_line[:137] + "…"
    snippet = stripped[:320]
    if len(stripped) > 320:
        snippet = snippet.rstrip() + "…"
    return {
        "chars": len(raw),
        "lines": lines,
        "headline": first_line or "(пусто)",
        "snippet": snippet if stripped else "—",
        "is_empty": not stripped,
    }


def build_chat_effective_prompt_context(*, data_dir: Path) -> dict[str, Any]:
    try:
        task_system = load_system_prompt()
    except Exception as exc:  # noqa: BLE001
        task_system = f"[Ошибка чтения system prompt: {exc}]"
    effective = merge_with_global_model_policy(task_system)
    runtime_tools = get_tools_for_runtime(data_dir=data_dir)
    runtime_tool_names: list[str] = []
    for schema in runtime_tools:
        fn = (schema.get("function") or {}).get("name")
        if isinstance(fn, str) and fn.strip():
            runtime_tool_names.append(fn.strip())
    return {
        "effective_system_prompt": effective,
        "runtime_tool_names": runtime_tool_names,
        "runtime_tools_json": json.dumps(runtime_tools, ensure_ascii=False, indent=2, default=str),
    }


def read_policy_files() -> dict[str, str]:
    from services.llm.system_prompt_loader import (
        get_dream_beat_planner_path,
        get_dream_decomposition_path,
        get_dream_scene_motion_decompose_path,
    )

    gp = get_global_model_policy_path()
    sp = get_system_prompt_path()
    dbeat = get_dream_beat_planner_path()
    dmotion = get_dream_scene_motion_decompose_path()
    dd = get_dream_decomposition_path()
    out: dict[str, str] = {}
    for key, path in (
        ("global_model_policy", gp),
        ("system_prompt", sp),
        ("dream_beat_planner", dbeat),
        ("dream_scene_motion_decompose", dmotion),
        ("dream_decomposition", dd),
    ):
        try:
            out[key] = path.read_text(encoding="utf-8") if path.is_file() else ""
        except OSError:
            out[key] = ""
    return out


def write_policy_file(which: str, content: str) -> None:
    from services.llm.system_prompt_loader import (
        get_dream_beat_planner_path,
        get_dream_decomposition_path,
        get_dream_scene_motion_decompose_path,
    )

    if which == "global_model_policy":
        path = get_global_model_policy_path()
    elif which == "system_prompt":
        path = get_system_prompt_path()
    elif which == "dream_beat_planner":
        path = get_dream_beat_planner_path()
    elif which == "dream_scene_motion_decompose":
        path = get_dream_scene_motion_decompose_path()
    elif which == "dream_decomposition":
        path = get_dream_decomposition_path()
    else:
        raise ValueError("unknown policy file")
    path.write_text(content, encoding="utf-8")


def build_tools_frame_context(
    *,
    data_dir: Path,
    chat_store: ChatStoreRepository,
    video_job_repo: VideoJobRepository,
    period: str = "month",
    custom_start: str | None = None,
    custom_end: str | None = None,
    registry_view: str = "grid",
    exec_tool: str | None = None,
    exec_status: str | None = None,
    exec_user: str | None = None,
    only_errors: bool = False,
    dream_run_repo: DreamRunRepository | None = None,
    dream_scene_repo: DreamSceneRepository | None = None,
    generated_frame_repo: GeneratedFrameRepository | None = None,
    scene_video_repo: SceneVideoRepository | None = None,
    story_video_repo: StoryVideoRepository | None = None,
    pipeline_job_id: str | None = None,
    usage_ledger_repo: DevUsageLedgerRepository | None = None,
) -> dict[str, Any]:
    """Данные для полной вкладки Tools (один HTMX-ответ)."""
    start, end = get_tools_period_bounds(
        period, custom_start=custom_start, custom_end=custom_end
    )
    try:
        video_agg = video_job_repo.aggregate_period_stats_sync(since=start, until=end)
    except Exception:  # noqa: BLE001
        video_agg = {"total": 0, "succeeded": 0, "failed": 0, "last_created": None}

    rows = build_registry_rows(
        data_dir=data_dir,
        chat_store=chat_store,
        period=period,
        custom_start=custom_start,
        custom_end=custom_end,
    )
    merge_video_stats_from_aggregate(rows, video_agg)

    executions = list_unified_executions(
        chat_store=chat_store,
        video_job_repo=video_job_repo,
        limit=80,
        period=period,
        custom_start=custom_start,
        custom_end=custom_end,
        tool_name=exec_tool or None,
        status_filter=exec_status or None,
        internal_user_id=exec_user or None,
        only_errors=only_errors,
        only_active=False,
    )
    live = list_unified_executions(
        chat_store=chat_store,
        video_job_repo=video_job_repo,
        limit=40,
        period=period,
        custom_start=custom_start,
        custom_end=custom_end,
        only_active=True,
    )
    pipeline_defs = pipeline_definitions()
    pipeline_jobs = list_pipeline_jobs(
        dream_run_repo=dream_run_repo,
        limit=80,
        only_active=False,
    )
    pipeline_live = list_pipeline_jobs(
        dream_run_repo=dream_run_repo,
        limit=40,
        only_active=True,
    )
    storage_summary = pipeline_storage_summary(
        dream_scene_repo=dream_scene_repo,
        frame_repo=generated_frame_repo,
        scene_video_repo=scene_video_repo,
        story_repo=story_video_repo,
    )
    selected_pipeline = pipeline_job_detail(
        run_id=pipeline_job_id,
        dream_run_repo=dream_run_repo,
        dream_scene_repo=dream_scene_repo,
        frame_repo=generated_frame_repo,
        scene_video_repo=scene_video_repo,
        story_repo=story_video_repo,
        video_job_repo=video_job_repo,
    )
    runtime_overview = pipeline_runtime_overview(dream_run_repo)
    enabled_pipeline_rows = [r for r in rows if r.get("type") == "pipeline" and bool(r.get("enabled", True))]
    enabled_pipeline_names = {str(r.get("name")) for r in enabled_pipeline_rows}
    filtered_pipeline_defs = [p for p in pipeline_defs if str(p.get("name")) in enabled_pipeline_names]
    prompt_dynamic_context = build_prompt_dynamic_context(
        atomic_rows=[r for r in rows if r.get("type") in ("atomic", "async_atomic")],
        pipeline_defs=filtered_pipeline_defs,
        runtime=runtime_overview,
    )
    policies_files = read_policy_files()
    policies_extra = load_policies_extra(data_dir)
    prompt_meta = {
        "system_prompt": prompt_file_meta(policies_files.get("system_prompt")),
        "global_model_policy": prompt_file_meta(
            policies_files.get("global_model_policy")
        ),
        "dream_beat_planner": prompt_file_meta(policies_files.get("dream_beat_planner")),
        "dream_scene_motion_decompose": prompt_file_meta(
            policies_files.get("dream_scene_motion_decompose")
        ),
        "dream_decomposition": prompt_file_meta(
            policies_files.get("dream_decomposition")
        ),
    }
    analytics = analytics_summary(
        chat_store=chat_store,
        video_job_repo=video_job_repo,
        data_dir=data_dir,
        period=period,
        custom_start=custom_start,
        custom_end=custom_end,
        video_agg=video_agg,
    )
    chat_effective = build_chat_effective_prompt_context(data_dir=data_dir)

    usage_ledger_rows: list[dict[str, Any]] = []
    if usage_ledger_repo is not None:
        try:
            usage_ledger_rows = usage_ledger_repo.aggregate_by_category_sync(
                since=start, until=end
            )
        except Exception:  # noqa: BLE001
            usage_ledger_rows = []
    try:
        chat_llm_usage = chat_store.aggregate_model_token_usage_global_sync(
            since=start, until=end
        )
    except Exception:  # noqa: BLE001
        chat_llm_usage = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    return {
        "registry_rows": rows,
        "atomic_tools": [r for r in rows if r.get("type") in ("atomic", "async_atomic")],
        "pipeline_registry_rows": [r for r in rows if r.get("type") == "pipeline"],
        "registry_view": (registry_view or "grid").lower(),
        "executions": executions,
        "live_items": live,
        "pipeline_definitions": pipeline_defs,
        "active_tool_names": [
            str(r.get("name"))
            for r in rows
            if bool(r.get("enabled", True))
        ],
        "pipeline_jobs": pipeline_jobs,
        "pipeline_live": pipeline_live,
        "pipeline_storage": storage_summary,
        "pipeline_runtime": runtime_overview,
        "selected_pipeline": selected_pipeline,
        "selected_pipeline_job_id": pipeline_job_id or "",
        "prompt_dynamic_context": prompt_dynamic_context,
        "policies": policies_files,
        "policies_extra": policies_extra,
        "prompt_meta": prompt_meta,
        "analytics": analytics,
        "period": period,
        "custom_start": custom_start or "",
        "custom_end": custom_end or "",
        "exec_tool": exec_tool or "",
        "exec_status": exec_status or "",
        "exec_user": exec_user or "",
        "only_errors": only_errors,
        "poll_interval_sec": 2.5,
        "usage_analytics": {
            "chat_llm": chat_llm_usage,
            "ledger_by_category": usage_ledger_rows,
        },
        "chat_effective_prompt": chat_effective,
    }
