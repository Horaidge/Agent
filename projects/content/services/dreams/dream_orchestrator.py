"""Главный пайплайн: сон → план сцен → кадры → Wan → склейка → Telegram.

Персистит dream_runs, dream_scenes, generated_frames, scene_videos для dev UI.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from aiogram.types import FSInputFile, Message

from core.config.settings import Settings
from core.observability.context import current_trace_id
from core.observability.service import ObservabilityService
from services.dreams.character_gate import (
    create_base_character_and_profile,
    user_declines_own_face,
)
from services.dreams.dream_scene_planner import (
    build_animation_prompts_for_scenes,
    build_visual_prompts_for_scenes,
    decompose_dream_scenes,
    merge_scene_plan,
)
from services.dreams.models import (
    DreamSceneItem,
    DreamScenePlan,
    DreamStage,
    DreamStageProgress,
    SceneFrameData,
)
from services.dreams.user_asset_context_service import UserAssetContextService
from services.telegram_reply_keyboards import main_reply_keyboard
from services.llm.openai_chat_service import OpenAIChatService
from services.tools.image_tools import tool_generate_image
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
from storage.user_profile_repository import UserProfileRepository

logger = logging.getLogger(__name__)

_VIDEO_MODEL = "wan2.7-i2v"
_IMG_SIZE = "1024*1536"


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


async def resolve_image_reference(
    ctx: dict[str, Any],
    dream_repo: DreamAssetRepository,
    scene: DreamSceneItem,
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
        url = (asset or {}).get("source_image_url")
        return ("base_character", base_id, url, "base_character · dream_assets")

    def _face() -> tuple[str, str | None, str | None, str] | None:
        if not faces:
            return None
        fa = faces[0]
        fid = fa.get("_id")
        return ("face_asset", str(fid) if fid else None, None, "face_asset · Telegram upload")

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

    # Явное намерение из шага 2
    if pref == "none":
        e = _env()
        if e:
            return e
        return ("none", None, None, "none · только текстовый промпт")

    if pref == "face":
        f = _face()
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
        f = _face()
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
    f = _face()
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

        system = (
            "Ты классификатор интентов. Верни ТОЛЬКО JSON-объект с полями: "
            "intent (dream|chat|text_generation|other), confidence (0..1), reason (кратко, по-русски)."
        )
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

        pending = await self._runs.find_awaiting_character(uid)
        if not pending:
            return False

        trace_id = current_trace_id.get() or "unknown"
        run_id = pending["_id"]
        dream_text = pending.get("dream_text") or ""

        low = text.lower()
        appearance: str | None
        if low in ("анон", "anon", "аноним", "анонимно"):
            appearance = None
        else:
            appearance = text

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
                "asset_context_snapshot": snap,
                "selected_character_asset_id": snap.get("selected_character_asset_id"),
                "error": None,
            },
        )
        try:
            await message.answer(
                "Персонаж сохранён. Запускаю визуализацию сна — это займёт несколько минут.",
                reply_markup=main_reply_keyboard(),
            )
        except Exception:
            pass

        asyncio.create_task(
            self._execute_pipeline_safe(message, dream_text, run_id, trace_id)
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

    async def _start_dream_from_text(
        self,
        message: Message,
        dream_text: str,
        trace_id: str,
    ) -> None:
        user = message.from_user
        uid = user.id if user else 0

        pending = await self._runs.find_awaiting_character(uid)
        if pending:
            await message.answer(
                "Уже ждём описание внешности для предыдущего запроса. "
                "Ответь одним сообщением или отправь **анон**.",
                parse_mode="Markdown",
                reply_markup=main_reply_keyboard(),
            )
            return

        await self._emit(trace_id, "dream.pipeline.started", {"user_id": uid, "dream_len": len(dream_text)})

        ctx = await self._user_ctx.build(uid)
        snap = await self._user_ctx.build_storage_snapshot(uid)
        ctx["_snapshot"] = snap

        has_id = bool(ctx.get("has_face")) or bool(ctx.get("has_base_character"))

        if not has_id:
            if user_declines_own_face(dream_text):
                try:
                    await create_base_character_and_profile(
                        user_id=uid,
                        chat_id=message.chat.id,
                        source_message_id=message.message_id,
                        appearance=None,
                        dream_repo=self._dream_assets,
                        user_profile_repo=self._profiles,
                    )
                    await self._emit(trace_id, "dream.base_character.generated", {"anon": True})
                    ctx = await self._user_ctx.build(uid)
                    snap = await self._user_ctx.build_storage_snapshot(uid)
                    ctx["_snapshot"] = snap
                except Exception as e:
                    logger.exception("dream: auto anon character")
                    await self._emit(
                        trace_id,
                        "dream.pipeline.failed",
                        {"stage": "base_character", "error": str(e)},
                    )
                    await message.answer(
                        f"Ошибка создания персонажа: {e!s}"[:4000],
                        reply_markup=main_reply_keyboard(),
                    )
                    return
            else:
                await self._runs.insert_one(
                    {
                        "user_id": uid,
                        "telegram_user_id": uid,
                        "chat_id": message.chat.id,
                        "trace_id": trace_id,
                        "dream_text": dream_text,
                        "status": "awaiting_character",
                        "scene_count": 0,
                        "asset_context_snapshot": snap,
                        "selected_character_asset_id": None,
                    }
                )
                await self._emit(
                    trace_id,
                    "dream.pipeline.waiting_character",
                    {},
                )
                await message.answer(
                    "Вижу intent на визуализацию сна. Чтобы персонаж был одинаковым во всех кадрах, "
                    "опиши коротко, как ты выглядишь (одним сообщением). "
                    "Либо отправь **анон** — тогда будет нейтральный герой без твоего лица.",
                    parse_mode="Markdown",
                    reply_markup=main_reply_keyboard(),
                )
                return

        rid = await self._runs.insert_one(
            {
                "user_id": uid,
                "telegram_user_id": uid,
                "chat_id": message.chat.id,
                "trace_id": trace_id,
                "dream_text": dream_text,
                "status": "started",
                "scene_count": 0,
                "asset_context_snapshot": snap,
                "selected_character_asset_id": snap.get("selected_character_asset_id"),
            }
        )

        try:
            await message.answer(
                "Понял, это похоже на сон. Запускаю визуализацию… Это может занять несколько минут.",
                reply_markup=main_reply_keyboard(),
            )
        except Exception:
            pass

        asyncio.create_task(self._execute_pipeline_safe(message, dream_text, rid, trace_id))

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

        ctx = await self._user_ctx.build(uid)
        snap = await self._user_ctx.build_storage_snapshot(uid)
        ctx["_snapshot"] = snap

        progress = DreamStageProgress()

        await self._runs.update(
            run_id,
            {
                "asset_context_snapshot": snap,
                "selected_character_asset_id": snap.get(
                    "selected_character_asset_id"
                ),
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
        progress: DreamStageProgress,
    ) -> tuple[DreamScenePlan, dict[int, str]]:
        progress.begin("stage_1", DreamStage.DECOMPOSING)
        await self._save_progress(run_id, progress, {"status": DreamStage.DECOMPOSING})

        # 1a) Декомпозиция на смысловые сцены
        dream_summary, outlines = await decompose_dream_scenes(
            openai=self._openai,
            dream_text=dream_text,
            asset_context=ctx,
        )
        await self._emit(
            trace_id,
            "dream.scenes.decomposed",
            {"run_id": run_id, "scene_count": len(outlines)},
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

        # 1c) Промпты анимации
        ap_map = await build_animation_prompts_for_scenes(
            openai=self._openai,
            dream_text=dream_text,
            outlines=outlines,
            visual_prompts_by_index=vp_map,
            asset_context=ctx,
        )
        await self._emit(
            trace_id,
            "dream.animation_prompts.ready",
            {"run_id": run_id, "scene_indices": sorted(ap_map.keys())},
        )

        # 1d) Мерж в финальный план
        plan = merge_scene_plan(dream_summary, outlines, vp_map, ap_map)

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

        frames: list[SceneFrameData] = []

        for sc in plan.scenes:
            dream_scene_id = scene_id_by_index.get(sc.scene_index, "")
            ref_type, ref_aid, ref_url, ref_label = await resolve_image_reference(
                ctx, self._dream_assets, sc
            )

            visual_raw = sc.visual_prompt
            full_prompt = f"{visual_raw}{suffix}".strip()
            if sc.environment_requirement:
                full_prompt += f" Setting: {sc.environment_requirement}."
            if sc.mood:
                full_prompt += f" Mood: {sc.mood}."

            prompt_inputs: dict[str, Any] = {
                "dream_text_fragment": dream_text[:4000],
                "visual_prompt_raw": visual_raw,
                "reference_type_intent": sc.reference_type or None,
                "character_prompt_suffix": suffix or None,
                "image_prompt_final": full_prompt,
                "mood": sc.mood,
                "environment_requirement": sc.environment_requirement,
                "character_requirement": sc.character_requirement,
                "reference_resolution": ref_label,
                "snapshot_at_generation": {
                    "has_face": snap.get("has_face"),
                    "has_base_character": snap.get("has_base_character"),
                },
            }

            _prompt_for_gen = full_prompt  # capture for closure

            def _gen(_p: str = _prompt_for_gen) -> str:
                last_err = ""
                for _ in range(2):
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
                    "image_url": image_url,
                    "related_character_id": char_id,
                    "related_environment": sc.environment_requirement,
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
                "animation_prompt_raw": sc.animation_prompt,
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
