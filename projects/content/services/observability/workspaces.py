"""Агрегации user workspaces для dev UI (поверх существующей MongoDB)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from storage.chat_repository import ChatStoreRepository
from storage.dream_asset_repository import DreamAssetRepository
from storage.dream_run_repository import DreamRunRepository
from storage.generated_frame_repository import GeneratedFrameRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.scene_video_repository import SceneVideoRepository
from storage.story_video_repository import StoryVideoRepository
from storage.video_job_repository import VideoJobRepository
from storage.repository import MessageRepository


@dataclass
class WorkspaceSummaryDTO:
    user_id: int
    chat_id: int | None
    first_seen: datetime | None
    last_activity: datetime | None
    message_count: int
    assistant_count: int
    model_calls_count: int
    tool_calls_count: int
    dream_assets_count: int
    generated_images_count: int
    generated_frames_count: int
    video_jobs_count: int
    dream_runs_count: int
    scene_videos_count: int
    story_videos_count: int
    failed_jobs_count: int
    error_events_count: int
    trace_sample: list[str]

    @property
    def artifact_count(self) -> int:
        return (
            self.dream_assets_count
            + self.generated_images_count
            + self.generated_frames_count
            + self.video_jobs_count
            + self.scene_videos_count
            + self.story_videos_count
        )

    @property
    def generation_count(self) -> int:
        return (
            self.generated_images_count
            + self.generated_frames_count
            + self.video_jobs_count
            + self.scene_videos_count
            + self.story_videos_count
        )

    @property
    def total_objects(self) -> int:
        return self.message_count + self.model_calls_count + self.tool_calls_count + self.artifact_count


def _period_bounds(
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


def _range_match(start: datetime | None, end: datetime | None) -> dict[str, Any]:
    if not start and not end:
        return {}
    created_q: dict[str, Any] = {}
    if start:
        created_q["$gte"] = start
    if end:
        created_q["$lte"] = end
    return {"created_at": created_q}


def _safe_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:  # noqa: BLE001
        return None


def _group_stats_by_user(
    coll: Any,
    user_field: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[int, dict[str, Any]]:
    pipeline: list[dict[str, Any]] = []
    rmatch = _range_match(start, end)
    if rmatch:
        pipeline.append({"$match": rmatch})
    pipeline.append(
        {
            "$group": {
                "_id": f"${user_field}",
                "count": {"$sum": 1},
                "first_seen": {"$min": "$created_at"},
                "last_seen": {"$max": "$created_at"},
            }
        }
    )
    out: dict[int, dict[str, Any]] = {}
    for row in coll.aggregate(pipeline):
        uid = _safe_int(row.get("_id"))
        if uid is None:
            continue
        out[uid] = {
            "count": int(row.get("count") or 0),
            "first_seen": row.get("first_seen"),
            "last_seen": row.get("last_seen"),
        }
    return out


def list_workspace_summaries(
    message_repo: MessageRepository,
    chat_store: ChatStoreRepository,
    dream_asset_repo: DreamAssetRepository,
    video_job_repo: VideoJobRepository,
    dream_run_repo: DreamRunRepository | None,
    generated_frame_repo: GeneratedFrameRepository | None,
    generated_image_repo: GeneratedImageRepository | None,
    scene_video_repo: SceneVideoRepository | None,
    story_video_repo: StoryVideoRepository | None,
    *,
    period: str = "all",
    sort_by: str = "last_activity",
    search: str = "",
    custom_start: str | None = None,
    custom_end: str | None = None,
    limit: int = 200,
) -> list[WorkspaceSummaryDTO]:
    start, end = _period_bounds(period, custom_start=custom_start, custom_end=custom_end)

    msg_stats = _group_stats_by_user(message_repo._sync, "telegram_user_id", start=start, end=end)  # type: ignore[attr-defined]
    conv_stats = _group_stats_by_user(chat_store._conv_s, "telegram_user_id", start=start, end=end)  # type: ignore[attr-defined]
    model_stats = _group_stats_by_user(chat_store._model_s, "internal_user_id", start=start, end=end)  # type: ignore[attr-defined]
    tool_stats = _group_stats_by_user(chat_store._tool_s, "internal_user_id", start=start, end=end)  # type: ignore[attr-defined]
    asset_stats = _group_stats_by_user(dream_asset_repo._sync, "owner_user_id", start=start, end=end)  # type: ignore[attr-defined]
    video_stats = _group_stats_by_user(video_job_repo._sync, "owner_user_id", start=start, end=end)  # type: ignore[attr-defined]
    frame_stats = _group_stats_by_user(generated_frame_repo._sync, "user_id", start=start, end=end) if generated_frame_repo else {}
    gen_img_stats = _group_stats_by_user(generated_image_repo._sync, "user_id", start=start, end=end) if generated_image_repo else {}
    run_stats = _group_stats_by_user(dream_run_repo._sync, "user_id", start=start, end=end) if dream_run_repo else {}
    sv_stats = _group_stats_by_user(scene_video_repo._sync, "user_id", start=start, end=end) if scene_video_repo else {}
    story_stats = _group_stats_by_user(story_video_repo._sync, "user_id", start=start, end=end) if story_video_repo else {}

    users = set()
    for s in (
        msg_stats, conv_stats, model_stats, tool_stats, asset_stats,
        video_stats, frame_stats, gen_img_stats, run_stats, sv_stats, story_stats
    ):
        users.update(s.keys())

    q = (search or "").strip().lower()
    out: list[WorkspaceSummaryDTO] = []
    for uid in users:
        chat_doc = message_repo._sync.find_one({"telegram_user_id": uid}, {"telegram_chat_id": 1})  # type: ignore[attr-defined]
        chat_id = _safe_int((chat_doc or {}).get("telegram_chat_id"))

        failed_jobs_count = int(
            video_job_repo._sync.count_documents({"owner_user_id": uid, "status": {"$in": ["failed", "error"]}})  # type: ignore[attr-defined]
        )
        error_events_count = int(
            message_repo._sync.count_documents({"telegram_user_id": uid, "status": "error"})  # type: ignore[attr-defined]
        )

        trace_sample = [
            str(x)
            for x in message_repo._sync.distinct("trace_id", {"telegram_user_id": uid, "trace_id": {"$ne": None}})[:8]  # type: ignore[attr-defined]
        ]

        first_seen = min(
            [
                v for v in (
                    msg_stats.get(uid, {}).get("first_seen"),
                    conv_stats.get(uid, {}).get("first_seen"),
                    model_stats.get(uid, {}).get("first_seen"),
                    tool_stats.get(uid, {}).get("first_seen"),
                    asset_stats.get(uid, {}).get("first_seen"),
                    video_stats.get(uid, {}).get("first_seen"),
                    frame_stats.get(uid, {}).get("first_seen"),
                    gen_img_stats.get(uid, {}).get("first_seen"),
                    run_stats.get(uid, {}).get("first_seen"),
                    sv_stats.get(uid, {}).get("first_seen"),
                    story_stats.get(uid, {}).get("first_seen"),
                )
                if v is not None
            ],
            default=None,
        )
        last_activity = max(
            [
                v for v in (
                    msg_stats.get(uid, {}).get("last_seen"),
                    conv_stats.get(uid, {}).get("last_seen"),
                    model_stats.get(uid, {}).get("last_seen"),
                    tool_stats.get(uid, {}).get("last_seen"),
                    asset_stats.get(uid, {}).get("last_seen"),
                    video_stats.get(uid, {}).get("last_seen"),
                    frame_stats.get(uid, {}).get("last_seen"),
                    gen_img_stats.get(uid, {}).get("last_seen"),
                    run_stats.get(uid, {}).get("last_seen"),
                    sv_stats.get(uid, {}).get("last_seen"),
                    story_stats.get(uid, {}).get("last_seen"),
                )
                if v is not None
            ],
            default=None,
        )

        dto = WorkspaceSummaryDTO(
            user_id=uid,
            chat_id=chat_id,
            first_seen=first_seen,
            last_activity=last_activity,
            message_count=int(msg_stats.get(uid, {}).get("count") or 0),
            assistant_count=int(
                chat_store._conv_s.count_documents({"telegram_user_id": uid, "role": "assistant"})  # type: ignore[attr-defined]
            ),
            model_calls_count=int(model_stats.get(uid, {}).get("count") or 0),
            tool_calls_count=int(tool_stats.get(uid, {}).get("count") or 0),
            dream_assets_count=int(asset_stats.get(uid, {}).get("count") or 0),
            generated_images_count=int(gen_img_stats.get(uid, {}).get("count") or 0),
            generated_frames_count=int(frame_stats.get(uid, {}).get("count") or 0),
            video_jobs_count=int(video_stats.get(uid, {}).get("count") or 0),
            dream_runs_count=int(run_stats.get(uid, {}).get("count") or 0),
            scene_videos_count=int(sv_stats.get(uid, {}).get("count") or 0),
            story_videos_count=int(story_stats.get(uid, {}).get("count") or 0),
            failed_jobs_count=failed_jobs_count,
            error_events_count=error_events_count,
            trace_sample=trace_sample,
        )

        if q:
            q_ok = (
                q in str(dto.user_id).lower()
                or (dto.chat_id is not None and q in str(dto.chat_id).lower())
                or any(q in str(t).lower() for t in dto.trace_sample)
            )
            if not q_ok:
                continue
        out.append(dto)

    key_map: dict[str, Any] = {
        "last_activity": lambda x: x.last_activity or datetime.min.replace(tzinfo=UTC),
        "messages": lambda x: x.message_count,
        "artifacts": lambda x: x.artifact_count,
        "generations": lambda x: x.generation_count,
        "created": lambda x: x.first_seen or datetime.min.replace(tzinfo=UTC),
        "size": lambda x: x.total_objects,
    }
    key_fn = key_map.get((sort_by or "").strip().lower(), key_map["last_activity"])
    out.sort(key=key_fn, reverse=True)
    return out[: max(1, min(limit, 500))]


def get_workspace_detail(
    user_id: int,
    message_repo: MessageRepository,
    chat_store: ChatStoreRepository,
    dream_asset_repo: DreamAssetRepository,
    video_job_repo: VideoJobRepository,
    dream_run_repo: DreamRunRepository | None,
    generated_frame_repo: GeneratedFrameRepository | None,
    generated_image_repo: GeneratedImageRepository | None,
    scene_video_repo: SceneVideoRepository | None,
    story_video_repo: StoryVideoRepository | None,
    *,
    limit: int = 300,
) -> dict[str, Any]:
    msgs = message_repo.list_messages_debug_sync(limit=limit, telegram_user_id=user_id)
    conv = chat_store.list_conversation_sync(str(user_id), limit=limit)
    m_calls = chat_store.list_model_calls_sync(str(user_id), limit=120)
    t_calls = chat_store.list_tool_calls_sync(str(user_id), limit=120)
    assets = dream_asset_repo.list_by_owner_sync(user_id, limit=120)
    vjobs = [
        d for d in video_job_repo.list_recent_sync(limit=200)
        if _safe_int(d.get("owner_user_id")) == user_id
    ]
    runs = []
    if dream_run_repo is not None:
        runs = [dict(x) for x in dream_run_repo._sync.find({"user_id": user_id}).sort("created_at", -1).limit(120)]  # type: ignore[attr-defined]
    frames = []
    if generated_frame_repo is not None:
        frames = [dict(x) for x in generated_frame_repo._sync.find({"user_id": user_id}).sort("created_at", -1).limit(120)]  # type: ignore[attr-defined]
    gimgs = []
    if generated_image_repo is not None:
        gimgs = [dict(x) for x in generated_image_repo._sync.find({"user_id": user_id}).sort("created_at", -1).limit(120)]  # type: ignore[attr-defined]
    scene_videos = []
    if scene_video_repo is not None:
        scene_videos = [dict(x) for x in scene_video_repo._sync.find({"user_id": user_id}).sort("created_at", -1).limit(120)]  # type: ignore[attr-defined]
    story_videos = []
    if story_video_repo is not None:
        story_videos = [dict(x) for x in story_video_repo._sync.find({"user_id": user_id}).sort("created_at", -1).limit(120)]  # type: ignore[attr-defined]

    def _ser_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for d in items:
            x = dict(d)
            oid = x.pop("_id", None)
            x["_id"] = str(oid) if oid is not None else None
            for k in ("created_at", "updated_at"):
                v = x.get(k)
                if hasattr(v, "isoformat"):
                    x[k] = v.isoformat()
            out.append(x)
        return out

    msgs_dict = [
        {
            "id": m.id,
            "created_at": m.created_at.isoformat(),
            "telegram_message_id": m.telegram_message_id,
            "message_type": m.message_type,
            "text": m.text,
            "trace_id": m.trace_id,
            "chat_id": m.telegram_chat_id,
        }
        for m in msgs
    ]

    all_dates: list[datetime] = []
    for m in msgs:
        all_dates.append(m.created_at.astimezone(UTC))
    for s in (conv, m_calls, t_calls, assets, vjobs, runs, frames, gimgs, scene_videos, story_videos):
        for it in s:
            dt = it.get("created_at")
            if isinstance(dt, datetime):
                all_dates.append(dt.astimezone(UTC))
            elif isinstance(dt, str):
                try:
                    all_dates.append(datetime.fromisoformat(dt).astimezone(UTC))
                except Exception:  # noqa: BLE001
                    pass

    first_seen = min(all_dates).isoformat() if all_dates else None
    last_seen = max(all_dates).isoformat() if all_dates else None

    return {
        "user_id": user_id,
        "chat_id": (msgs[0].telegram_chat_id if msgs else None),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "summary": {
            "messages_total": len(msgs_dict),
            "assistant_responses": sum(1 for x in conv if x.get("role") == "assistant"),
            "model_calls": len(m_calls),
            "tool_calls": len(t_calls),
            "dream_assets": len(assets),
            "generated_images": len(gimgs),
            "generated_frames": len(frames),
            "video_jobs": len(vjobs),
            "dream_runs": len(runs),
            "scene_videos": len(scene_videos),
            "story_videos": len(story_videos),
            "failed_jobs": sum(1 for x in vjobs if str(x.get("status", "")).lower() in ("failed", "error")),
        },
        "messages": msgs_dict,
        "conversation": _ser_list(conv),
        "model_calls": _ser_list(m_calls),
        "tool_calls": _ser_list(t_calls),
        "dream_assets": _ser_list(assets),
        "generated_images": _ser_list(gimgs),
        "generated_frames": _ser_list(frames),
        "video_jobs": _ser_list(vjobs),
        "dream_runs": _ser_list(runs),
        "scene_videos": _ser_list(scene_videos),
        "story_videos": _ser_list(story_videos),
    }

