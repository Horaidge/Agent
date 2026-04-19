"""
Dev UI: реестр инструментов, агрегаты по MongoDB и лёгкие overrides на диске.

Источники данных (без новых коллекций):
- статический каталог из `services.tools.openai_definitions` + метаданные;
- `tool_calls`, `video_jobs`;
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
)
from services.tools.openai_definitions import OPENAI_TOOLS_CATALOG
from storage.chat_repository import ChatStoreRepository
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


# обратная совместимость внутри модуля
_period_bounds = get_period_bounds


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
        is_async = fn in ("generate_dream_pipeline", "image_to_video")
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
            }
        )

    # image_to_video: статистика из video_jobs (если есть вызовы без chat tool_calls)
    # считаем все джобы за период как «вызовы» инструмента
    return rows


def merge_video_job_stats_for_registry(
    *,
    video_job_repo: VideoJobRepository,
    rows: list[dict[str, Any]],
    since: datetime | None,
    until: datetime | None = None,
) -> None:
    try:
        jobs = video_job_repo.list_filtered_sync(limit=5000, since=since, until=until)
    except Exception:  # noqa: BLE001
        return
    total = len(jobs)
    ok = sum(1 for j in jobs if (j.get("status") or "") == "succeeded")
    last_ts = None
    for j in jobs:
        ca = j.get("created_at")
        if hasattr(ca, "isoformat"):
            last_ts = max(last_ts, ca) if last_ts else ca
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
        steps = [
            {"id": "queued", "title": "Queued", "status": "ok" if raw_st != "failed" else "skip"},
            {"id": "provider", "title": "Sent to provider", "status": "ok" if raw_st in ("running", "succeeded", "failed") else "pending"},
            {"id": "poll", "title": "Polling", "status": "ok" if raw_st in ("succeeded", "failed") else ("running" if raw_st == "running" else "pending")},
            {"id": "result", "title": "Result", "status": "ok" if raw_st == "succeeded" else ("failed" if raw_st == "failed" else "pending")},
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
) -> dict[str, Any]:
    start, end = _period_bounds(period, custom_start=custom_start, custom_end=custom_end)
    since = start
    until = end
    stats = chat_store.aggregate_tool_stats_global_sync(since=since, until=until)
    total_calls = sum(int(s.get("total") or 0) for s in stats)
    total_ok = sum(int(s.get("success") or 0) for s in stats)
    failed = total_calls - total_ok
    jobs = video_job_repo.list_filtered_sync(limit=5000, since=since, until=until)
    j_fail = sum(1 for j in jobs if (j.get("status") or "") == "failed")
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
        "total_calls": total_calls + len(jobs),
        "failed_calls": failed + j_fail,
        "avg_latency_ms": None,
        "p95_latency_ms": None,
        "top_tools": top,
        "series": series,
        "tool_stats": stats,
    }


def read_policy_files() -> dict[str, str]:
    gp = get_global_model_policy_path()
    sp = get_system_prompt_path()
    out: dict[str, str] = {}
    for key, path in (("global_model_policy", gp), ("system_prompt", sp)):
        try:
            out[key] = path.read_text(encoding="utf-8") if path.is_file() else ""
        except OSError:
            out[key] = ""
    return out


def write_policy_file(which: str, content: str) -> None:
    if which == "global_model_policy":
        path = get_global_model_policy_path()
    elif which == "system_prompt":
        path = get_system_prompt_path()
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
) -> dict[str, Any]:
    """Данные для полной вкладки Tools (один HTMX-ответ)."""
    rows = build_registry_rows(
        data_dir=data_dir,
        chat_store=chat_store,
        period=period,
        custom_start=custom_start,
        custom_end=custom_end,
    )
    start, end = get_period_bounds(period, custom_start=custom_start, custom_end=custom_end)
    merge_video_job_stats_for_registry(
        video_job_repo=video_job_repo,
        rows=rows,
        since=start,
        until=end,
    )

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
    policies_files = read_policy_files()
    policies_extra = load_policies_extra(data_dir)
    analytics = analytics_summary(
        chat_store=chat_store,
        video_job_repo=video_job_repo,
        data_dir=data_dir,
        period=period,
        custom_start=custom_start,
        custom_end=custom_end,
    )

    return {
        "registry_rows": rows,
        "registry_view": (registry_view or "grid").lower(),
        "executions": executions,
        "live_items": live,
        "policies": policies_files,
        "policies_extra": policies_extra,
        "analytics": analytics,
        "period": period,
        "custom_start": custom_start or "",
        "custom_end": custom_end or "",
        "exec_tool": exec_tool or "",
        "exec_status": exec_status or "",
        "exec_user": exec_user or "",
        "only_errors": only_errors,
        "poll_interval_sec": 2.5,
    }
