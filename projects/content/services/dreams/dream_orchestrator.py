"""Главный пайплайн: сон → план сцен → кадры → Wan → склейка → Telegram.

Персистит dream_runs, dream_scenes, generated_frames, scene_videos для dev UI.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from aiogram.types import FSInputFile, Message
from pydantic import ValidationError

from core.config.settings import Settings
from core.observability.context import current_trace_id
from core.observability.service import ObservabilityService
from services.assets.asset_source_service import resolve_dream_asset_image_ref_for_qwen
from services.assets.dream_asset_service import ASSET_TYPE_CHARACTER, STATUS_GENERATED
from services.dreams.character_gate import (
    create_base_character_and_profile,
    user_declines_own_face,
)
from services.dreams.dream_scene_planner import (
    build_visual_prompts_for_scenes,
    decompose_dream_scenes,
    merge_scene_plan,
)
from services.dreams.models import (
    DreamSceneItem,
    DreamSceneOutline,
    DreamScenePlan,
    DreamStage,
    DreamStageProgress,
    SceneFrameData,
)
from services.dreams.user_asset_context_service import UserAssetContextService
from services.telegram_reply_keyboards import main_reply_keyboard
from services.llm.openai_chat_service import OpenAIChatService
from services.llm.system_prompt_loader import read_dream_intent_routing_raw
from services.tools.image_tools import (
    tool_edit_image,
    tool_generate_base_character,
    tool_generate_image,
)
from services.video.final_video_assembler import (
    FinalVideoAssemblerError,
    assemble_remote_mp4s,
)
from services.video.video_job_service import VideoJobService
from storage.dream_asset_repository import DreamAssetRepository
from storage.dream_run_repository import DreamRunRepository
from storage.dream_scene_repository import DreamSceneRepository
from storage.generated_frame_repository import GeneratedFrameRepository
from storage.scene_video_repository import SceneVideoRepository
from storage.story_video_repository import StoryVideoRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.user_profile_repository import UserProfileRepository

logger = logging.getLogger(__name__)

_VIDEO_MODEL = "wan2.7-i2v"
_IMG_SIZE = "1024*1536"
_START_FRAME_PREFIX = (
    "First frame only — opening beat, start of the action, not the final frozen pose. "
)
_DEFAULT_STYLE_PRESET = "dream_cinematic"
_MAX_SECONDARY_ACTORS = 3

# Если `prompts/dream_intent_routing.md` пуст — только для аварийного fallback.
_FALLBACK_DREAM_INTENT_SYSTEM = (
    "Ты классификатор интентов. Верни ТОЛЬКО JSON-объект с полями: "
    "intent (dream|chat|text_generation|other), confidence (0..1), reason (кратко, по-русски)."
)

# Строки «я» в actors Stage 0 — не второстепенные ассеты (сопоставление без отдельного LLM).
_PRIMARY_ACTOR_EXCLUDE = frozenset(
    {"я", "пользователь", "главный герой", "сновидец", "рассказчик"}
)


def _dream_intent_system_prompt() -> str:
    raw = (read_dream_intent_routing_raw() or "").strip()
    return raw if raw else _FALLBACK_DREAM_INTENT_SYSTEM


def _asset_id_for_actor_name(
    ctx: dict[str, Any],
    actor_bindings: dict[str, str],
    name: str,
) -> str | None:
    k = _actor_key(name)
    if actor_bindings.get(k):
        return str(actor_bindings[k])
    if actor_bindings.get(name):
        return str(actor_bindings[name])
    for a in ctx.get("secondary_actors") or []:
        if _actor_key(str(a.get("actor_name") or "")) == k:
            aid = a.get("_id")
            return str(aid) if aid else None
    return None


def _secondary_actor_names_from_outlines(outlines: list[DreamSceneOutline]) -> list[str]:
    """Кого просим описать как secondary: только из Stage 0, порядок — первое появление."""
    seen: set[str] = set()
    out: list[str] = []
    for o in outlines:
        for raw in o.actors or []:
            n = str(raw or "").strip()
            if not n:
                continue
            key = _actor_key(n)
            if key in _PRIMARY_ACTOR_EXCLUDE:
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(n)
            if len(out) >= _MAX_SECONDARY_ACTORS:
                return out
    return out


def _character_prompt_suffix(ctx: dict[str, Any]) -> str:
    snap = ctx.get("_snapshot") or ctx
    if snap.get("has_base_character") or ctx.get("base_character_asset_id"):
        return (
            " same person as reference, consistent face, "
            "same character identity across scenes."
        )
    return ""


def _norm_scene_reference_pref(raw: str) -> str:
    x = (raw or "").strip().lower()
    if x in ("face", "face_asset"):
        return "face"
    if x in ("base_character", "none"):
        return x
    return ""


def _actor_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _parse_style_input(raw: str) -> dict[str, str]:
    t = (raw or "").strip()
    if not t:
        return {"preset": _DEFAULT_STYLE_PRESET, "custom_prompt": ""}
    low = t.lower()
    known = {"dream_cinematic", "anime", "noir", "realistic", "surreal"}
    if low in known:
        return {"preset": low, "custom_prompt": ""}
    if low.startswith("preset:"):
        p = low.replace("preset:", "", 1).strip() or _DEFAULT_STYLE_PRESET
        return {"preset": p, "custom_prompt": ""}
    return {"preset": _DEFAULT_STYLE_PRESET, "custom_prompt": t}


def _build_style_block(style: dict[str, Any] | None) -> str:
    s = style or {}
    preset = str(s.get("preset") or _DEFAULT_STYLE_PRESET)
    custom = str(s.get("custom_prompt") or "").strip()
    out = f"style preset: {preset}"
    if custom:
        out += f"; style custom: {custom}"
    return out


async def resolve_image_reference(
    ctx: dict[str, Any],
    dream_repo: DreamAssetRepository,
    scene: DreamSceneItem,
    *,
    bot_token: str = "",
) -> tuple[str, str | None, str | None, str]:
    """
    Тип reference для UI: base_character | face_asset | environment_asset | none.
    Возвращает (type, asset_id, preview_url, human_label).

    Если scene.reference_type задан (шаг 2 pipeline), учитываем намерение модели:
    base_character — сначала базовый персонаж; face — сначала загруженное лицо;
    none — без лица/базы, только окружение при необходимости или чистый текст.
    """
    prof = ctx.get("user_profile") or {}
    base_id = prof.get("base_character_asset_id") or ctx.get("base_character_asset_id")
    faces = ctx.get("face_assets") or []
    envs = ctx.get("environment_assets") or []
    pref = _norm_scene_reference_pref(scene.reference_type)

    async def _base() -> tuple[str, str | None, str | None, str] | None:
        if not base_id:
            return None
        asset = await dream_repo.find_by_id(base_id)
        if not asset:
            return None
        url = resolve_dream_asset_image_ref_for_qwen(asset, bot_token=bot_token)
        if not url:
            return None
        return ("base_character", str(base_id), url, "base_character · dream_assets")

    async def _face() -> tuple[str, str | None, str | None, str] | None:
        if not faces:
            return None
        for fa in faces:
            furl = resolve_dream_asset_image_ref_for_qwen(fa, bot_token=bot_token)
            if not furl:
                continue
            fid = fa.get("_id")
            return (
                "face_asset",
                str(fid) if fid else None,
                furl,
                "face_asset · dream_assets (URL или data URI из Telegram)",
            )
        return None

    def _env() -> tuple[str, str | None, str | None, str] | None:
        if not envs or not (scene.environment_requirement or "").strip():
            return None
        ea = envs[0]
        eid = ea.get("_id")
        return (
            "environment_asset",
            str(eid) if eid else None,
            None,
            "environment_asset · опора на окружение (без URL кадра)",
        )

    cr = (scene.character_requirement or "").strip().lower()
    # Сцена только с окружением / без людей — не навязываем эталон лица.
    scene_is_env_only = cr in ("none",)

    # Явное намерение из шага 2
    if pref == "none":
        # Модель часто ставит reference_type=none при том, что в сцене есть герой:
        # если есть база/лицо — принудительно цепляемся к эталону для консистентности.
        if not scene_is_env_only:
            b = await _base()
            if b:
                return b
            f = await _face()
            if f:
                return f
        e = _env()
        if e:
            return e
        return ("none", None, None, "none · только текстовый промпт")

    if pref == "face":
        f = await _face()
        if f:
            return f
        b = await _base()
        if b:
            return b
        e = _env()
        if e:
            return e
        return ("none", None, None, "none · только текстовый промпт")

    if pref == "base_character":
        b = await _base()
        if b:
            return b
        f = await _face()
        if f:
            return f
        e = _env()
        if e:
            return e
        return ("none", None, None, "none · только текстовый промпт")

    # Авто (как раньше): база → лицо → окружение
    b = await _base()
    if b:
        return b
    f = await _face()
    if f:
        return f
    e = _env()
    if e:
        return e
    return ("none", None, None, "none · только текстовый промпт")


class DreamPipelineService:
    def __init__(
        self,
        settings: Settings,
        *,
        dream_run_repo: DreamRunRepository,
        dream_scene_repo: DreamSceneRepository,
        frame_repo: GeneratedFrameRepository,
        scene_video_repo: SceneVideoRepository,
        story_repo: StoryVideoRepository,
        dream_asset_repo: DreamAssetRepository,
        user_profile_repo: UserProfileRepository,
        user_context: UserAssetContextService,
        video_jobs: VideoJobService,
        openai: OpenAIChatService,
        observability: ObservabilityService | None = None,
        generated_image_repo: GeneratedImageRepository | None = None,
    ) -> None:
        self._settings = settings
        self._runs = dream_run_repo
        self._scenes = dream_scene_repo
        self._frames = frame_repo
        self._scene_videos = scene_video_repo
        self._story = story_repo
        self._dream_assets = dream_asset_repo
        self._profiles = user_profile_repo
        self._user_ctx = user_context
        self._video = video_jobs
        self._openai = openai
        self._obs = observability
        self._generated_images = generated_image_repo

    async def detect_intent_and_maybe_start(self, message: Message) -> bool:
        """
        Определяет intent входящего текста и при dream-intent запускает pipeline без /dream.
        Возвращает True, если сообщение обработано dream-модулем (включая уточняющий вопрос).
        """
        user = message.from_user
        uid = user.id if user else 0
        text = (message.text or "").strip()
        if not text:
            return False

        if await self.try_consume_appearance_message(message):
            return True

        trace_id = current_trace_id.get() or "unknown"
        intent = await self._detect_intent(text)
        await self._emit(
            trace_id,
            "dream.intent.detected",
            {"intent": intent.get("intent"), "confidence": intent.get("confidence")},
        )

        intent_name = str(intent.get("intent") or "chat").lower()
        confidence = float(intent.get("confidence") or 0.0)
        if intent_name != "dream" or confidence < 0.45:
            return False

        await self._start_dream_from_text(message, text, trace_id)
        return True

    async def _detect_intent(self, text: str) -> dict[str, Any]:
        low = text.lower()
        heuristic = any(
            x in low
            for x in (
                "мне приснилось",
                "приснилось",
                "я видел сон",
                "сон про",
                "во сне",
                "dream",
            )
        )
        if not self._openai.configured:
            return {"intent": "dream" if heuristic else "chat", "confidence": 0.6 if heuristic else 0.2}

        system = _dream_intent_system_prompt()
        user = (
            "Определи интент сообщения пользователя.\n"
            f"Сообщение:\n{text}\n"
            "Если это описание сна/сюжета сна или явный запрос визуализации сна — intent=dream."
        )
        try:
            raw = await self._openai.json_completion(system=system, user=user)
            import json

            obj = json.loads(raw)
            return {
                "intent": str(obj.get("intent") or "chat").lower(),
                "confidence": float(obj.get("confidence") or 0.0),
                "reason": str(obj.get("reason") or ""),
            }
        except Exception:
            logger.exception("dream intent detection failed")
            return {"intent": "dream" if heuristic else "chat", "confidence": 0.55 if heuristic else 0.2}

    async def _emit(
        self,
        trace_id: str,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if self._obs:
            await self._obs.record_dream_pipeline_event(
                trace_id=trace_id,
                event_type=event_type,
                detail=detail,
            )

    async def try_consume_appearance_message(self, message: Message) -> bool:
        user = message.from_user
        uid = user.id if user else 0
        text = (message.text or "").strip()
        if not text:
            return False

        pending = await self._runs.find_pending_input(uid)
        if not pending:
            return False

        trace_id = current_trace_id.get() or "unknown"
        run_id = str(pending["_id"])
        dream_text = str(pending.get("dream_text") or "")
        status = str(pending.get("status") or "")

        if status == "awaiting_style":
            style = _parse_style_input(text)
            await self._runs.update(
                run_id,
                {
                    "style": style,
                    "status": "started",
                    "current_stage": "resolve_style_complete",
                    "pending_input": None,
                },
            )
            await message.answer(
                "Стиль сохранен. Продолжаю подготовку пайплайна.",
                reply_markup=main_reply_keyboard(),
            )
            await self._maybe_wait_for_avatar_or_actors(
                message=message,
                run_id=run_id,
                trace_id=trace_id,
                dream_text=dream_text,
            )
            return True

        if status == "awaiting_actors":
            pending_input = pending.get("pending_input") or {}
            missing = list(pending_input.get("missing_actor_names") or [])
            resolved = dict(pending_input.get("resolved_actor_ids") or {})
            if not missing:
                await self._runs.update(
                    run_id,
                    {
                        "status": "started",
                        "pending_input": None,
                    },
                )
                await self._maybe_wait_for_avatar_or_actors(
                    message=message,
                    run_id=run_id,
                    trace_id=trace_id,
                    dream_text=dream_text,
                )
                return True
            actor_name = str(missing[0])
            appearance = None if text.lower() in ("анон", "anon", "аноним", "анонимно") else text
            actor_id = await self._create_secondary_actor(
                user_id=uid,
                chat_id=message.chat.id,
                source_message_id=message.message_id,
                actor_name=actor_name,
                appearance=appearance,
            )
            resolved[_actor_key(actor_name)] = actor_id
            remaining = missing[1:]
            if remaining:
                await self._runs.update(
                    run_id,
                    {
                        "pending_input": {
                            "kind": "actors",
                            "missing_actor_names": remaining,
                            "resolved_actor_ids": resolved,
                        }
                    },
                )
                await message.answer(
                    f"Сохранён актёр `{actor_name}`. Опиши теперь `{remaining[0]}` (или отправь `анон`).",
                    parse_mode="Markdown",
                    reply_markup=main_reply_keyboard(),
                )
                return True
            await self._runs.update(
                run_id,
                {
                    "status": "started",
                    "pending_input": None,
                    "actor_bindings": resolved,
                    "current_stage": "resolve_actors_complete",
                },
            )
            await message.answer(
                "Актёры сохранены. Запускаю визуализацию сна.",
                reply_markup=main_reply_keyboard(),
            )
            await self._maybe_wait_for_avatar_or_actors(
                message=message,
                run_id=run_id,
                trace_id=trace_id,
                dream_text=dream_text,
            )
            return True

        low = text.lower()
        appearance: str | None
        if low in ("анон", "anon", "аноним", "анонимно"):
            appearance = None
        else:
            appearance = text

        # awaiting_character fallback
        try:
            await create_base_character_and_profile(
                user_id=uid,
                chat_id=message.chat.id,
                source_message_id=message.message_id,
                appearance=appearance,
                dream_repo=self._dream_assets,
                user_profile_repo=self._profiles,
            )
            await self._emit(
                trace_id,
                "dream.base_character.generated",
                {"run_id": run_id, "anon": appearance is None},
            )
        except Exception as e:
            logger.exception("dream: base character failed")
            await self._runs.update(
                run_id,
                {"status": "failed", "error": str(e)},
            )
            await self._emit(
                trace_id,
                "dream.pipeline.failed",
                {"stage": "base_character", "error": str(e)},
            )
            try:
                await message.answer(
                    f"Не удалось создать персонажа: {e!s}"[:4000],
                    reply_markup=main_reply_keyboard(),
                )
            except Exception:
                logger.exception("telegram answer failed")
            return True

        snap = await self._user_ctx.build_storage_snapshot(uid)
        await self._runs.update(
            run_id,
            {
                "status": "started",
                "current_stage": "resolve_avatar_complete",
                "asset_context_snapshot": snap,
                "selected_character_asset_id": snap.get("selected_character_asset_id"),
                "error": None,
                "pending_input": None,
            },
        )
        await self._maybe_wait_for_avatar_or_actors(
            message=message,
            run_id=run_id,
            trace_id=trace_id,
            dream_text=dream_text,
        )
        return True

    async def handle_dream_command(self, message: Message) -> None:
        user = message.from_user
        uid = user.id if user else 0
        raw = message.text or ""
        parts = raw.split(maxsplit=1)
        dream_text = parts[1].strip() if len(parts) > 1 else ""

        trace_id = current_trace_id.get() or "unknown"

        if not dream_text:
            await message.answer(
                "Опиши сон обычным сообщением — я сам запущу визуализацию, когда увижу описание сна.",
                reply_markup=main_reply_keyboard(),
            )
            return

        await self._start_dream_from_text(message, dream_text, trace_id)

    async def run_from_dev(
        self,
        *,
        user_id: int,
        dream_text: str,
        chat_id: int | None = None,
        decompose_model: str | None = None,
    ) -> str:
        """Dev-only запуск pipeline без Telegram update (для UI inspector).

        decompose_model — опционально: модель Stage 0 из allowlist (см. Settings).
        """
        uid = int(user_id)
        cid = int(chat_id or user_id)
        trace_id = f"dev-{uuid.uuid4().hex}"

        class _DevBot:
            async def send_video(self, *args: Any, **kwargs: Any) -> None:
                return None

        class _DevFromUser:
            def __init__(self, x: int) -> None:
                self.id = x

        class _DevChat:
            def __init__(self, x: int) -> None:
                self.id = x

        class _DevMessage:
            def __init__(self, u: int, c: int, text: str) -> None:
                self.from_user = _DevFromUser(u)
                self.chat = _DevChat(c)
                self.text = text
                self.message_id = 0
                self.bot = _DevBot()

            async def answer(self, *args: Any, **kwargs: Any) -> None:
                return None

        msg = _DevMessage(uid, cid, dream_text.strip())
        await self._start_dream_from_text(
            msg,
            dream_text.strip(),
            trace_id,
            decompose_model_override=decompose_model,
        )

        pending = await self._runs.find_by_trace(trace_id)
        if pending and str(pending.get("status")) == "awaiting_style":
            run_id = str(pending.get("_id") or "")
            await self._runs.update(
                run_id,
                {
                    "style": {"preset": _DEFAULT_STYLE_PRESET, "custom_prompt": ""},
                    "status": "started",
                    "current_stage": "resolve_style_complete",
                    "pending_input": None,
                },
            )
            await self._maybe_wait_for_avatar_or_actors(
                message=msg,
                run_id=run_id,
                trace_id=trace_id,
                dream_text=dream_text.strip(),
            )

        run_id = ""
        for _ in range(20):
            await asyncio.sleep(0.15)
            got = await self._runs.find_by_trace(trace_id)
            if got and got.get("_id"):
                run_id = str(got["_id"])
                break
        return run_id

    async def start_from_tool_call(
        self,
        *,
        message: Message,
        dream_text: str,
        trace_id: str,
        style_hint: str | None = None,
    ) -> dict[str, Any]:
        """Запуск dream pipeline из model tool-call в основном chat-потоке."""
        await self._start_dream_from_text(
            message,
            dream_text.strip(),
            trace_id,
            style_hint=style_hint,
        )
        run = await self._runs.find_by_trace(trace_id)
        if not run:
            return {
                "ok": True,
                "run_id": None,
                "status": "started",
            }
        return {
            "ok": True,
            "run_id": str(run.get("_id") or ""),
            "status": str(run.get("status") or "started"),
            "trace_id": trace_id,
        }

    async def _load_or_run_stage0_decompose(
        self,
        *,
        run_id: str,
        trace_id: str,
        dream_text: str,
        ctx: dict[str, Any],
        clear_precomputed_after_cache_hit: bool = False,
    ) -> tuple[str, list[DreamSceneOutline]]:
        """
        Единственный вызов декомпозиции (prompts/dream_scene_motion_decompose.md): либо из кэша run,
        либо json_completion. Кэш нужен между «собрать второстепенных» и полным pipeline.
        """
        run_doc = await self._runs.find_by_id(run_id) or {}
        snap_data = run_doc.get("decomposition_snapshot") or {}
        scenes_raw = snap_data.get("scenes")
        if (
            run_doc.get("stage0_precomputed")
            and isinstance(scenes_raw, list)
            and scenes_raw
        ):
            dream_summary = str(snap_data.get("dream_summary") or "")
            outlines: list[DreamSceneOutline] = []
            for s in scenes_raw:
                if not isinstance(s, dict):
                    continue
                try:
                    outlines.append(DreamSceneOutline.model_validate(dict(s)))
                except ValidationError:
                    logger.warning("dream: кэш Stage 0 невалиден, повторная декомпозиция")
                    outlines = []
                    break
            if outlines:
                if clear_precomputed_after_cache_hit:
                    await self._runs.update(run_id, {"stage0_precomputed": False})
                logger.info(
                    "dream: Stage 0 из кэша run_id=%s scenes=%d",
                    run_id,
                    len(outlines),
                )
                return dream_summary, outlines

        run_doc = await self._runs.find_by_id(run_id) or {}
        override = run_doc.get("dream_decompose_model_override")
        decompose_model = self._settings.resolve_dream_decompose_model(override)
        if not self._openai.configured:
            raise RuntimeError("OPENAI_API_KEY не задан — нельзя разобрать сон")
        dream_summary, outlines = await decompose_dream_scenes(
            openai=self._openai,
            dream_text=dream_text,
            asset_context=ctx,
            model=decompose_model,
        )
        await self._runs.update(
            run_id,
            {
                "dream_summary": dream_summary,
                "dream_decompose_model": decompose_model,
                "decomposition_snapshot": {
                    "dream_summary": dream_summary,
                    "scenes": [o.model_dump() for o in outlines],
                },
                "stage0_precomputed": True,
            },
        )
        await self._emit(
            trace_id,
            "dream.scenes.decomposed",
            {
                "run_id": run_id,
                "scene_count": len(outlines),
                "decompose_model": decompose_model,
                "from_cache": False,
            },
        )
        if clear_precomputed_after_cache_hit:
            await self._runs.update(run_id, {"stage0_precomputed": False})
        return dream_summary, outlines

    async def _create_secondary_actor(
        self,
        *,
        user_id: int,
        chat_id: int,
        source_message_id: int,
        actor_name: str,
        appearance: str | None,
    ) -> str:
        bc = tool_generate_base_character(appearance)
        if not bc.ok or not bc.image_url:
            raise RuntimeError(bc.error or "secondary_actor_generation_failed")
        doc: dict[str, Any] = {
            "owner_user_id": user_id,
            "telegram_user_id": user_id,
            "chat_id": chat_id,
            "source_message_id": source_message_id,
            "asset_type": ASSET_TYPE_CHARACTER,
            "status": STATUS_GENERATED,
            "is_secondary_actor": True,
            "actor_name": actor_name,
            "actor_name_key": _actor_key(actor_name),
            "source_image_url": bc.image_url,
            "prompt_used": bc.prompt_used,
            "character_uuid": bc.character_id,
        }
        return await self._dream_assets.insert_one(doc)

    async def _maybe_wait_for_avatar_or_actors(
        self,
        *,
        message: Message,
        run_id: str,
        trace_id: str,
        dream_text: str,
    ) -> None:
        uid = message.from_user.id if message.from_user else 0
        ctx = await self._user_ctx.build(uid)
        snap = await self._user_ctx.build_storage_snapshot(uid)
        ctx["_snapshot"] = snap
        has_id = bool(ctx.get("has_face")) or bool(ctx.get("has_base_character"))
        if not has_id:
            # Legacy flow removed: не ждём ручного описания внешности.
            # Если у пользователя нет базового персонажа, создаём анонимный профиль автоматически.
            await create_base_character_and_profile(
                user_id=uid,
                chat_id=message.chat.id,
                source_message_id=message.message_id,
                appearance=None,
                dream_repo=self._dream_assets,
                user_profile_repo=self._profiles,
            )
            snap = await self._user_ctx.build_storage_snapshot(uid)

        run_doc_pre = await self._runs.find_by_id(run_id) or {}
        merged_bindings: dict[str, str] = dict(run_doc_pre.get("actor_bindings") or {})
        for a in ctx.get("secondary_actors") or []:
            an = str(a.get("actor_name") or "").strip()
            aid = a.get("_id")
            if an and aid:
                merged_bindings[_actor_key(an)] = str(aid)

        try:
            _, outlines = await self._load_or_run_stage0_decompose(
                run_id=run_id,
                trace_id=trace_id,
                dream_text=dream_text,
                ctx=ctx,
                clear_precomputed_after_cache_hit=False,
            )
        except Exception as e:
            logger.exception("dream: Stage 0 до запуска pipeline не удался")
            await self._runs.update(
                run_id,
                {"status": "failed", "error": str(e)},
            )
            await self._emit(
                trace_id,
                "dream.pipeline.failed",
                {"stage": "stage0_pre_gate", "error": str(e)},
            )
            try:
                await message.answer(
                    f"Не удалось разобрать сон: {e!s}"[:4000],
                    reply_markup=main_reply_keyboard(),
                )
            except Exception:
                logger.warning("dream: error reply failed", exc_info=True)
            return

        ctx = await self._user_ctx.build(uid)
        snap = await self._user_ctx.build_storage_snapshot(uid)
        ctx["_snapshot"] = snap
        for a in ctx.get("secondary_actors") or []:
            an = str(a.get("actor_name") or "").strip()
            aid = a.get("_id")
            if an and aid:
                merged_bindings[_actor_key(an)] = str(aid)
        run_doc_pre = await self._runs.find_by_id(run_id) or {}
        merged_bindings = {**merged_bindings, **dict(run_doc_pre.get("actor_bindings") or {})}

        needed = _secondary_actor_names_from_outlines(outlines)
        missing: list[str] = []
        for n in needed:
            if not _asset_id_for_actor_name(ctx, merged_bindings, n):
                missing.append(n)
        missing = missing[:_MAX_SECONDARY_ACTORS]
        if missing:
            # Legacy flow removed: не останавливаем pipeline на ручном вводе второстепенных актёров.
            logger.info(
                "dream: продолжаем без ручного ввода secondary actors run_id=%s missing=%s",
                run_id,
                missing,
            )

        await self._runs.update(
            run_id,
            {
                "status": "started",
                "current_stage": "decomposition",
                "pending_input": None,
                "actor_bindings": merged_bindings,
                "asset_context_snapshot": snap,
                "selected_character_asset_id": snap.get("selected_character_asset_id"),
            },
        )
        await message.answer(
            "Понял, запускаю визуализацию сна. Это может занять несколько минут.",
            reply_markup=main_reply_keyboard(),
        )
        asyncio.create_task(self._execute_pipeline_safe(message, dream_text, run_id, trace_id))

    async def _start_dream_from_text(
        self,
        message: Message,
        dream_text: str,
        trace_id: str,
        style_hint: str | None = None,
        decompose_model_override: str | None = None,
    ) -> None:
        user = message.from_user
        uid = user.id if user else 0

        pending = await self._runs.find_pending_input(uid)
        if pending:
            await message.answer(
                "Есть незавершённый run (ожидается ввод по персонажам). "
                "Заверши его одним сообщением.",
                parse_mode="Markdown",
                reply_markup=main_reply_keyboard(),
            )
            return

        await self._emit(trace_id, "dream.pipeline.started", {"user_id": uid, "dream_len": len(dream_text)})

        # dream_text — канонический сырой ввод пользователя; не перезаписывать summary/декомпозицией.
        run_doc: dict[str, Any] = {
            "user_id": uid,
            "telegram_user_id": uid,
            "chat_id": message.chat.id,
            "trace_id": trace_id,
            "dream_text": dream_text,
            "status": "started",
            "scene_count": 0,
            "style": _parse_style_input(style_hint or ""),
            "asset_context_snapshot": {},
            "selected_character_asset_id": None,
            "pending_input": None,
            "actor_bindings": {},
            "current_stage": "load_user_context",
        }
        if decompose_model_override is not None and str(decompose_model_override).strip():
            run_doc["dream_decompose_model_override"] = (
                self._settings.resolve_dream_decompose_model(decompose_model_override)
            )
        rid = await self._runs.insert_one(run_doc)
        await self._maybe_wait_for_avatar_or_actors(
            message=message,
            run_id=rid,
            trace_id=trace_id,
            dream_text=dream_text,
        )

    async def _execute_pipeline_safe(
        self,
        message: Message,
        dream_text: str,
        run_id: str,
        trace_id: str,
    ) -> None:
        try:
            await self._execute_pipeline(message, dream_text, run_id, trace_id)
        except Exception as e:
            logger.exception("dream pipeline failed")
            await self._runs.update(
                run_id,
                {
                    "status": DreamStage.FAILED,
                    "current_stage": DreamStage.FAILED,
                    "error": str(e),
                },
            )
            await self._emit(
                trace_id,
                "dream.pipeline.failed",
                {"error": str(e)},
            )
            try:
                await message.answer(
                    f"Не удалось завершить визуализацию сна: {e!s}"[:4000],
                    reply_markup=main_reply_keyboard(),
                )
            except Exception:
                logger.exception("dream: error reply failed")

    # ------------------------------------------------------------------
    # Helpers: progress tracking & user notifications
    # ------------------------------------------------------------------

    async def _save_progress(
        self,
        run_id: str,
        progress: DreamStageProgress,
        extra: dict[str, Any] | None = None,
    ) -> None:
        patch: dict[str, Any] = {
            "current_stage": progress.current_stage,
            "stage_progress": progress.model_dump()["stages"],
        }
        if extra:
            patch.update(extra)
        await self._runs.update(run_id, patch)

    async def _notify_user(self, message: Message, text: str) -> None:
        try:
            await message.answer(text, reply_markup=main_reply_keyboard())
        except Exception:
            logger.warning("dream: telegram notification failed", exc_info=True)

    # ------------------------------------------------------------------
    # Pipeline coordinator
    # ------------------------------------------------------------------

    async def _execute_pipeline(
        self,
        message: Message,
        dream_text: str,
        run_id: str,
        trace_id: str,
    ) -> None:
        uid = message.from_user.id if message.from_user else 0
        chat_id = message.chat.id
        run_doc = await self._runs.find_by_id(run_id)
        style = (run_doc or {}).get("style") or {
            "preset": _DEFAULT_STYLE_PRESET,
            "custom_prompt": "",
        }
        actor_bindings = dict((run_doc or {}).get("actor_bindings") or {})

        ctx = await self._user_ctx.build(uid)
        snap = await self._user_ctx.build_storage_snapshot(uid)
        ctx["_snapshot"] = snap
        ctx["style"] = style
        ctx["actor_bindings"] = actor_bindings

        progress = DreamStageProgress()

        await self._runs.update(
            run_id,
            {
                "asset_context_snapshot": snap,
                "selected_character_asset_id": snap.get(
                    "selected_character_asset_id"
                ),
                "style": style,
                "actor_bindings": actor_bindings,
                "current_stage": progress.current_stage,
                "stage_progress": progress.model_dump()["stages"],
            },
        )

        # ── Stage 1: Разбор сна на сцены ─────────────────────────────
        plan, scene_id_by_index = await self._stage_1_decompose(
            dream_text=dream_text,
            run_id=run_id,
            trace_id=trace_id,
            ctx=ctx,
            snap=snap,
            actor_bindings=actor_bindings,
            progress=progress,
        )
        n = len(plan.scenes)
        await self._notify_user(
            message,
            f"Сон разобран на {n} {_scene_word(n)}. Генерирую изображения…",
        )

        # ── Stage 2: Генерация изображений ────────────────────────────
        frame_data = await self._stage_2_generate_images(
            plan=plan,
            dream_text=dream_text,
            run_id=run_id,
            trace_id=trace_id,
            uid=uid,
            ctx=ctx,
            snap=snap,
            scene_id_by_index=scene_id_by_index,
            message=message,
            progress=progress,
        )
        await self._notify_user(
            message,
            f"Изображения готовы ({len(frame_data)} из {n}). Запускаю анимацию…",
        )

        # ── Stage 3: Анимация ─────────────────────────────────────────
        video_urls, video_job_ids = await self._stage_3_animate(
            plan=plan,
            frame_data=frame_data,
            dream_text=dream_text,
            run_id=run_id,
            trace_id=trace_id,
            uid=uid,
            message=message,
            progress=progress,
        )
        await self._notify_user(
            message,
            "Анимация завершена. Собираю финальное видео…",
        )

        # ── Stage 4: Финальная сборка ─────────────────────────────────
        await self._stage_4_assemble(
            video_urls=video_urls,
            video_job_ids=video_job_ids,
            run_id=run_id,
            trace_id=trace_id,
            uid=uid,
            chat_id=chat_id,
            message=message,
            progress=progress,
        )

    # ------------------------------------------------------------------
    # Stage 1 — Разбор сна на сцены (3 LLM-вызова + persist)
    # ------------------------------------------------------------------

    async def _stage_1_decompose(
        self,
        *,
        dream_text: str,
        run_id: str,
        trace_id: str,
        ctx: dict[str, Any],
        snap: dict[str, Any],
        actor_bindings: dict[str, str],
        progress: DreamStageProgress,
    ) -> tuple[DreamScenePlan, dict[int, str]]:
        progress.begin("stage_1", DreamStage.DECOMPOSING)
        await self._save_progress(run_id, progress, {"status": DreamStage.DECOMPOSING})

        # 1a) Декомпозиция — тот же результат, что после гейта персонажей (кэш или один вызов)
        dream_summary, outlines = await self._load_or_run_stage0_decompose(
            run_id=run_id,
            trace_id=trace_id,
            dream_text=dream_text,
            ctx=ctx,
            clear_precomputed_after_cache_hit=True,
        )
        run_doc_pre = await self._runs.find_by_id(run_id)
        decompose_model = str((run_doc_pre or {}).get("dream_decompose_model") or "")
        logger.info(
            "dream pipeline Stage 0: model=%s (chat/image default=%s)",
            decompose_model or "(unknown)",
            self._settings.openai_model,
        )

        scene_id_by_index: dict[int, str] = {}
        for o in outlines:
            sid = await self._scenes.insert_one(
                {
                    "dream_run_id": run_id,
                    "trace_id": trace_id,
                    "scene_index": o.scene_index,
                    "title": o.title,
                    "short_description": (
                        o.short_description or o.scene_description
                    )[:600],
                    "scene_description": o.scene_description,
                    "mood": o.mood,
                    "duration_sec": o.duration_sec,
                    "environment_requirement": o.environment_requirement,
                    "character_requirement": o.character_requirement,
                    "actors": list(o.actors or []),
                    "actor_ids": [
                        actor_bindings.get(a) or actor_bindings.get(_actor_key(a))
                        for a in (o.actors or [])
                        if (actor_bindings.get(a) or actor_bindings.get(_actor_key(a)))
                    ],
                    "planning_payload": {
                        "pipeline_stage": "decomposed",
                        "outline": o.model_dump(),
                    },
                }
            )
            scene_id_by_index[o.scene_index] = sid

        progress.stages["stage_1"]["total"] = len(outlines)

        # 1b) Промпты изображений
        vp_map = await build_visual_prompts_for_scenes(
            openai=self._openai,
            dream_text=dream_text,
            dream_summary=dream_summary,
            outlines=outlines,
            asset_context=ctx,
        )
        await self._emit(
            trace_id,
            "dream.image_prompts.ready",
            {"run_id": run_id, "scene_indices": sorted(vp_map.keys())},
        )

        for o in outlines:
            vp_row = vp_map.get(o.scene_index) or ("", "")
            v_str, ref_from_llm = vp_row[0], vp_row[1]
            await self._scenes.update_by_run_and_index(
                run_id,
                o.scene_index,
                {
                    "planning_payload": {
                        "pipeline_stage": "image_prompts",
                        "outline": o.model_dump(),
                        "visual_prompt": v_str,
                        "reference_type": ref_from_llm,
                    },
                },
            )

        # 1c) Анимация задаётся только полем motion в декомпозиции (отдельный LLM не вызываем)

        # 1d) Мерж в финальный план
        plan = merge_scene_plan(dream_summary, outlines, vp_map)

        for sc in plan.scenes:
            await self._scenes.update_by_run_and_index(
                run_id,
                sc.scene_index,
                {
                    "title": sc.title,
                    "short_description": (
                        sc.short_description or sc.scene_description
                    )[:600],
                    "scene_description": sc.scene_description,
                    "mood": sc.mood,
                    "duration_sec": sc.duration_sec,
                    "environment_requirement": sc.environment_requirement,
                    "character_requirement": sc.character_requirement,
                    "actors": list(sc.actors or []),
                    "actor_ids": [
                        actor_bindings.get(a) or actor_bindings.get(_actor_key(a))
                        for a in (sc.actors or [])
                        if (actor_bindings.get(a) or actor_bindings.get(_actor_key(a)))
                    ],
                    "planning_payload": {
                        "pipeline_stage": "complete",
                        "scene": sc.model_dump(),
                    },
                },
            )

        await self._emit(
            trace_id,
            "dream.scene_plan.created",
            {
                "run_id": run_id,
                "scene_count": len(plan.scenes),
                "summary": plan.dream_summary[:500],
            },
        )

        progress.finish("stage_1", DreamStage.DECOMPOSED)
        await self._save_progress(
            run_id,
            progress,
            {
                "status": DreamStage.DECOMPOSED,
                "scene_count": len(plan.scenes),
                "dream_summary": plan.dream_summary,
            },
        )

        return plan, scene_id_by_index

    # ------------------------------------------------------------------
    # Stage 2 — Генерация изображений (по одному на сцену)
    # ------------------------------------------------------------------

    async def _stage_2_generate_images(
        self,
        *,
        plan: DreamScenePlan,
        dream_text: str,
        run_id: str,
        trace_id: str,
        uid: int,
        ctx: dict[str, Any],
        snap: dict[str, Any],
        scene_id_by_index: dict[int, str],
        message: Message,
        progress: DreamStageProgress,
    ) -> list[SceneFrameData]:
        total = len(plan.scenes)
        progress.begin("stage_2", DreamStage.GENERATING_IMAGES, total=total)
        await self._save_progress(run_id, progress, {"status": DreamStage.GENERATING_IMAGES})

        suffix = _character_prompt_suffix(ctx)
        prof = ctx.get("user_profile") or {}
        char_id = prof.get("base_character_asset_id")
        style_block = _build_style_block(ctx.get("style"))
        actor_bindings = dict(ctx.get("actor_bindings") or {})

        frames: list[SceneFrameData] = []

        for sc in plan.scenes:
            dream_scene_id = scene_id_by_index.get(sc.scene_index, "")
            ref_type, ref_aid, ref_url, ref_label = await resolve_image_reference(
                ctx,
                self._dream_assets,
                sc,
                bot_token=self._settings.telegram_bot_token or "",
            )

            visual_raw = sc.visual_prompt
            actor_names = list(sc.actors or [])
            actor_ids = [
                actor_bindings.get(a) or actor_bindings.get(_actor_key(a))
                for a in actor_names
                if (actor_bindings.get(a) or actor_bindings.get(_actor_key(a)))
            ]
            actor_block = ""
            if actor_names:
                actor_block = f" secondary actors: {', '.join(actor_names)}."
            full_prompt = (
                f"{_START_FRAME_PREFIX}{visual_raw}{suffix}. "
                "main character must remain consistent across all scenes."
                f"{actor_block} {style_block}"
            ).strip()
            if sc.environment_requirement:
                full_prompt += f" Setting: {sc.environment_requirement}."
            if sc.mood:
                full_prompt += f" Mood: {sc.mood}."

            ref_url_dbg = ref_url
            prompt_inputs: dict[str, Any] = {
                "dream_text_fragment": dream_text[:4000],
                "visual_prompt_raw": visual_raw,
                "reference_type_intent": sc.reference_type or None,
                "character_prompt_suffix": suffix or None,
                "style_block": style_block,
                "scene_actor_names": actor_names,
                "scene_actor_ids": actor_ids,
                "image_prompt_final": full_prompt,
                "image_role": "start_frame_for_video",
                "motion": sc.motion.model_dump(),
                "mood": sc.mood,
                "environment_requirement": sc.environment_requirement,
                "character_requirement": sc.character_requirement,
                "reference_resolution": ref_label,
                "reference_resolved_url": (
                    None
                    if not ref_url_dbg
                    else (
                        "[data URI, см. reference_image_url в кадре]"
                        if str(ref_url_dbg).startswith("data:")
                        else ref_url_dbg
                    )
                ),
                "snapshot_at_generation": {
                    "has_face": snap.get("has_face"),
                    "has_base_character": snap.get("has_base_character"),
                },
            }

            _prompt_for_gen = full_prompt  # capture for closure
            _ref_type = ref_type
            _ref_url = ref_url

            def _gen(_p: str = _prompt_for_gen, _rt: str = _ref_type, _ru: str | None = _ref_url) -> str:
                last_err = ""
                _ru_s = str(_ru or "").strip()
                _has_ref_url = bool(
                    _ru_s.startswith(("http://", "https://", "data:"))
                )
                for _ in range(2):
                    if _has_ref_url and _rt in ("base_character", "face_asset"):
                        # Если есть эталонный image reference, используем image-edit,
                        # чтобы удерживать идентичность лица между сценами.
                        r = tool_edit_image(
                            image_source=_ru_s,
                            instruction=_p,
                            size=_IMG_SIZE,
                            model="qwen-image-2.0",
                            n=1,
                        )
                    else:
                        r = tool_generate_image(
                            prompt=_p,
                            size=_IMG_SIZE,
                            model="qwen-image-2.0",
                            n=1,
                        )
                    if r.ok and r.image_urls:
                        return r.image_urls[0]
                    last_err = r.error or "image generation failed"
                raise RuntimeError(last_err)

            t0 = datetime.now(timezone.utc)
            image_url = await asyncio.to_thread(_gen)
            t1 = datetime.now(timezone.utc)

            _ru_s = str(ref_url or "").strip()
            uses_edit = bool(
                _ru_s.startswith(("http://", "https://", "data:"))
                and ref_type in ("base_character", "face_asset")
            )
            image_api_preview: dict[str, Any] = {
                "provider": "DashScope multimodal-generation/generation",
                "model": "qwen-image-2.0",
                "parameters": {"size": _IMG_SIZE, "n": 1, "watermark": False},
                "intent": "start_frame_for_video",
                "call": (
                    "edit_image — в input одно изображение-референс + текстовая инструкция"
                    if uses_edit
                    else "generate_image — только текстовый промпт в input"
                ),
            }

            await self._emit(
                trace_id,
                "dream.frame.generated",
                {"scene_index": sc.scene_index, "image_url": image_url[:200]},
            )

            fid = await self._frames.insert_one(
                {
                    "user_id": uid,
                    "trace_id": trace_id,
                    "dream_run_id": run_id,
                    "scene_id": dream_scene_id,
                    "scene_index": sc.scene_index,
                    "title": sc.title,
                    "image_prompt_raw": visual_raw,
                    "image_prompt_final": full_prompt,
                    "prompt_inputs": prompt_inputs,
                    "reference_type": ref_type,
                    "reference_asset_id": ref_aid,
                    "reference_image_url": ref_url,
                    "reference_label": ref_label,
                    "image_generation_mode": "edit_image" if uses_edit else "generate_image",
                    "image_api_request_preview": image_api_preview,
                    "image_url": image_url,
                    "related_character_id": char_id,
                    "related_environment": sc.environment_requirement,
                    "actor_ids": actor_ids,
                    "actor_names": actor_names,
                    "status": "generated",
                    "generation_started_at": t0,
                    "generation_completed_at": t1,
                }
            )

            frames.append(
                SceneFrameData(
                    scene_index=sc.scene_index,
                    scene=sc,
                    dream_scene_id=dream_scene_id,
                    frame_id=fid,
                    image_url=image_url,
                )
            )

            if self._generated_images:
                try:
                    await self._generated_images.insert_one(
                        user_id=uid,
                        image_url=image_url,
                        prompt=full_prompt,
                        related_character_id=char_id,
                    )
                except Exception:
                    logger.warning(
                        "dream: generated_images mirror insert failed",
                        exc_info=True,
                    )

            progress.tick("stage_2")
            await self._save_progress(run_id, progress)
            await self._notify_user(
                message,
                f"Изображение {len(frames)}/{total}",
            )

        progress.finish("stage_2", DreamStage.IMAGES_COMPLETE)
        await self._save_progress(run_id, progress, {"status": DreamStage.IMAGES_COMPLETE})

        return frames

    # ------------------------------------------------------------------
    # Stage 3 — Анимация (по одному видео на сцену)
    # ------------------------------------------------------------------

    async def _stage_3_animate(
        self,
        *,
        plan: DreamScenePlan,
        frame_data: list[SceneFrameData],
        dream_text: str,
        run_id: str,
        trace_id: str,
        uid: int,
        message: Message,
        progress: DreamStageProgress,
    ) -> tuple[list[str], list[str]]:
        total = len(frame_data)
        progress.begin("stage_3", DreamStage.ANIMATING, total=total)
        await self._save_progress(run_id, progress, {"status": DreamStage.ANIMATING})

        video_job_ids: list[str] = []
        scene_video_ids: list[str] = []

        # 3a) Отправляем все сцены на анимацию
        for fd in frame_data:
            sc = fd.scene
            anim_prompt = (
                sc.animation_prompt or sc.scene_description or dream_text[:500]
            )
            dur = min(max(sc.duration_sec, 4), 6)

            anim_inputs: dict[str, Any] = {
                "source_frame_id": fd.frame_id,
                "source_image_url": fd.image_url,
                "motion": sc.motion.model_dump(),
                "motion_source": "stage_0_decomposition",
                "animation_prompt_text": sc.animation_prompt,
                "animation_prompt_final": anim_prompt,
                "scene_excerpt": sc.scene_description[:1500],
            }
            extra: dict[str, Any] = {
                "dream_trace_id": trace_id,
                "dream_run_id": run_id,
                "scene_index": sc.scene_index,
                "frame_id": fd.frame_id,
                "source": "dream_pipeline",
            }

            await self._emit(
                trace_id,
                "dream.frame.animation_started",
                {"scene_index": sc.scene_index, "frame_id": fd.frame_id},
            )

            _ap = anim_prompt
            _iu = fd.image_url
            _d = dur
            _ex = extra

            def _create_vj(
                _uid: int = uid,
                _prompt: str = _ap,
                _img: str = _iu,
                _dur: int = _d,
                _extra: dict[str, Any] = _ex,
            ) -> str:
                return self._video.create_video_job(
                    owner_user_id=str(_uid),
                    prompt=_prompt,
                    image_url=_img,
                    model=_VIDEO_MODEL,
                    duration=_dur,
                    resolution="720p",
                    extra=_extra,
                )

            job_id = await asyncio.to_thread(_create_vj)
            job_doc = await asyncio.to_thread(self._video.get_job, job_id)
            prov = (job_doc or {}).get("provider_task_id")

            svid = await self._scene_videos.insert_one(
                {
                    "dream_run_id": run_id,
                    "scene_id": fd.dream_scene_id,
                    "trace_id": trace_id,
                    "scene_index": sc.scene_index,
                    "animation_prompt": anim_prompt,
                    "animation_inputs": anim_inputs,
                    "source_frame_id": fd.frame_id,
                    "source_image_url": fd.image_url,
                    "video_job_id": job_id,
                    "provider_task_id": prov,
                    "video_url": None,
                    "status": (job_doc or {}).get("status") or "running",
                    "model": _VIDEO_MODEL,
                    "duration": dur,
                    "resolution": "720p",
                }
            )

            await self._frames.update_one(
                fd.frame_id,
                {
                    "video_job_id": job_id,
                    "scene_video_id": svid,
                    "status": "animating",
                },
            )
            video_job_ids.append(job_id)
            scene_video_ids.append(svid)

        await self._runs.update(
            run_id,
            {"video_job_ids": video_job_ids},
        )

        # 3b) Ожидаем завершения каждой анимации
        video_urls: list[str] = []
        scene_vid_docs = await self._scene_videos.list_by_dream_run(run_id)

        for idx, sc in enumerate(plan.scenes):
            match = next(
                (
                    d
                    for d in scene_vid_docs
                    if d.get("scene_index") == sc.scene_index
                ),
                None,
            )
            if not match:
                continue
            jid = match.get("video_job_id")
            svid = match.get("_id")
            if not jid:
                continue

            doc = await asyncio.to_thread(
                self._video.poll_job_until_done,
                jid,
                timeout_sec=1800.0,
                interval_sec=4.0,
            )
            if doc.get("status") != "succeeded":
                raise RuntimeError(
                    doc.get("error") or f"Wan job failed: {jid}"
                )
            u = doc.get("video_url")
            if not u:
                raise RuntimeError(f"Нет video_url в job {jid}")
            video_urls.append(str(u))

            if svid:
                await self._scene_videos.update(
                    str(svid),
                    {
                        "video_url": str(u),
                        "status": "succeeded",
                        "provider_task_id": doc.get("provider_task_id"),
                    },
                )
            await self._emit(
                trace_id,
                "dream.frame.animation_completed",
                {"job_id": jid},
            )

            progress.tick("stage_3")
            await self._save_progress(run_id, progress)
            await self._notify_user(
                message,
                f"Анимация {idx + 1}/{total}",
            )

        progress.finish("stage_3", DreamStage.ANIMATION_COMPLETE)
        await self._save_progress(
            run_id, progress, {"status": DreamStage.ANIMATION_COMPLETE}
        )

        return video_urls, video_job_ids

    # ------------------------------------------------------------------
    # Stage 4 — Финальная сборка и отправка
    # ------------------------------------------------------------------

    async def _stage_4_assemble(
        self,
        *,
        video_urls: list[str],
        video_job_ids: list[str],
        run_id: str,
        trace_id: str,
        uid: int,
        chat_id: int,
        message: Message,
        progress: DreamStageProgress,
    ) -> None:
        progress.begin("stage_4", DreamStage.ASSEMBLING, total=1)
        await self._save_progress(run_id, progress, {"status": DreamStage.ASSEMBLING})

        out_dir = self._settings.data_dir / "outputs" / "story_videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{trace_id}.mp4"

        try:
            await asyncio.to_thread(
                assemble_remote_mp4s,
                video_urls,
                out_path,
                temp_dir=self._settings.data_dir / "temp",
            )
        except FinalVideoAssemblerError as e:
            await self._emit(
                trace_id,
                "dream.pipeline.failed",
                {"stage": "assemble", "error": str(e)},
            )
            if video_urls:
                await self._notify_user(
                    message,
                    "Не удалось склеить ролик (ffmpeg). Отправляю первый фрагмент.",
                )
                try:
                    await message.answer_video(
                        video_urls[0],
                        reply_markup=main_reply_keyboard(),
                    )
                except Exception:
                    await message.answer(
                        video_urls[0][:4000],
                        reply_markup=main_reply_keyboard(),
                    )
            raise

        await self._emit(
            trace_id, "dream.video.assembled", {"path": str(out_path)}
        )

        sv_id = await self._story.insert_one(
            {
                "user_id": uid,
                "trace_id": trace_id,
                "dream_run_id": run_id,
                "source_scene_video_job_ids": video_job_ids,
                "final_video_path": str(out_path),
                "final_video_url": None,
                "status": "completed",
            }
        )

        progress.finish("stage_4", DreamStage.COMPLETED)
        await self._save_progress(
            run_id,
            progress,
            {
                "status": DreamStage.COMPLETED,
                "story_video_id": sv_id,
                "completed_at": datetime.now(timezone.utc),
            },
        )

        await self._emit(
            trace_id,
            "dream.pipeline.completed",
            {"story_video_id": sv_id},
        )

        try:
            await message.bot.send_video(
                chat_id,
                video=FSInputFile(out_path),
                caption="Ваш сон визуализирован",
                reply_markup=main_reply_keyboard(),
            )
        except Exception:
            logger.exception("send_video failed, fallback URL")
            await message.answer(
                "Ваш сон визуализирован (файл на сервере). "
                "Ошибка отправки видео в Telegram.",
                reply_markup=main_reply_keyboard(),
            )


def _scene_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "сцену"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "сцены"
    return "сцен"
