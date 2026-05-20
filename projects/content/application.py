"""Сборка FastAPI: webhook Telegram + Gradio, lifespan, ресурсы."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

# До import gradio: отключаем телеметрию (иначе запросы к api.gradio.app / HF)
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "false")

from core.config.settings import detach_gradio_root_path_env, get_settings

detach_gradio_root_path_env()

from aiogram import Dispatcher
from fastapi import FastAPI
import gradio as gr

from bot.asset_handlers import create_dream_asset_router
from bot.dream_lite_handlers import router as dream_lite_telegram_router
from bot.dream_lite_middleware import DreamLiteResourcesMiddleware
from bot.handlers import router as telegram_router
from bot.media_handlers import router as media_log_router
from bot.middlewares import MessageServiceMiddleware
from bot.telegram_access_middleware import TelegramAccessMiddleware
from bot.user_menu_handlers import router as user_menu_router
from bot.user_menu_middleware import UserDataServiceMiddleware
from bot.webhook import register_telegram_webhook
from bot.webhook_management import set_webhook_from_settings
from core.integrations.telegram_client import create_telegram_bot
from core.logging_dev_filter import install_dev_access_log_filter
from core.observability.repository import ensure_observability_indexes
from core.tunnels.cloudflare_tunnel import (
    get_current_tunnel_url,
    read_persisted_tunnel_base_url,
    start_cloudflare_tunnel_background,
    stop_cloudflare_tunnel,
    wait_for_cloudflare_tunnel_url,
    wait_for_persisted_tunnel_base_url,
)
from services.assets.dream_asset_service import DreamAssetService
from services.chat.chat_orchestrator import ChatOrchestrator
from services.dreams.dream_orchestrator import DreamPipelineService
from services.dreams.user_asset_context_service import UserAssetContextService
from services.llm.openai_chat_service import OpenAIChatService
from services.message_service import MessageService
from services.user_data_service import UserDataService
from services.video.video_job_service import VideoJobService
from storage.chat_repository import ensure_chat_indexes
from storage.dev_usage_ledger_repository import ensure_dev_usage_ledger_indexes
from storage.dream_asset_repository import ensure_dream_asset_indexes
from storage.generated_image_repository import ensure_generated_image_indexes
from storage.filesystem import ensure_data_dirs
from storage.dream_lite_artifact_repository import ensure_dream_lite_artifact_indexes
from storage.dream_lite_asset_repository import ensure_dream_lite_asset_indexes
from storage.dream_lite_run_repository import (
    ensure_dream_lite_profile_indexes,
    ensure_dream_lite_run_indexes,
)
from storage.dream_lite_summary_repository import ensure_dream_lite_summary_indexes
from storage.dream_lite_step3_snapshot_repository import ensure_dream_lite_step3_snapshot_indexes
from storage.dream_run_repository import ensure_dream_run_indexes
from storage.dream_scene_repository import ensure_dream_scene_indexes
from storage.generated_frame_repository import ensure_generated_frame_indexes
from storage.mongo import (
    build_chat_store,
    build_dev_usage_ledger_repository,
    build_dream_asset_repository,
    build_dream_lite_artifact_repository,
    build_dream_lite_asset_repository,
    build_dream_lite_run_repository,
    build_dream_lite_step3_snapshot_repository,
    build_dream_lite_summary_repository,
    build_dream_run_repository,
    build_dream_scene_repository,
    build_generated_frame_repository,
    build_generated_image_repository,
    build_message_repository,
    build_observability,
    build_scene_video_repository,
    build_story_video_repository,
    build_telegram_access_repository,
    build_user_profile_repository,
    build_video_job_repository,
)
from storage.scene_video_repository import ensure_scene_video_indexes
from storage.story_video_repository import ensure_story_video_indexes
from storage.user_profile_repository import ensure_user_profile_indexes
from storage.repository import ensure_indexes
from storage.video_job_repository import ensure_video_job_indexes
from api.dream_lite_montage_json import build_dream_lite_montage_json_router
from ui.banner import print_local_app_banner, schedule_open_gradio_in_browser
from ui.gradio_app import build_gradio_app
from ui.prompts_editor_api import create_prompts_editor_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    install_dev_access_log_filter()
    settings = get_settings()
    ensure_data_dirs(settings)
    motor_client, sync_client, repository = build_message_repository(settings)
    chat_store = build_chat_store(settings, motor_client, sync_client)
    dream_asset_repo = build_dream_asset_repository(
        settings, motor_client, sync_client
    )
    video_job_repo = build_video_job_repository(
        settings, motor_client, sync_client
    )
    user_profile_repo = build_user_profile_repository(
        settings, motor_client, sync_client
    )
    generated_image_repo = build_generated_image_repository(
        settings, motor_client, sync_client
    )
    generated_frame_repo = build_generated_frame_repository(
        settings, motor_client, sync_client
    )
    dream_run_repo = build_dream_run_repository(
        settings, motor_client, sync_client
    )
    dream_lite_run_repo = build_dream_lite_run_repository(
        settings, motor_client, sync_client
    )
    dream_lite_artifact_repo = build_dream_lite_artifact_repository(
        settings, motor_client, sync_client
    )
    dream_lite_summary_repo = build_dream_lite_summary_repository(
        settings, motor_client, sync_client
    )
    dream_lite_asset_repo = build_dream_lite_asset_repository(
        settings, motor_client, sync_client
    )
    dream_lite_step3_snapshot_repo = build_dream_lite_step3_snapshot_repository(
        settings, sync_client
    )
    dream_scene_repo = build_dream_scene_repository(
        settings, motor_client, sync_client
    )
    scene_video_repo = build_scene_video_repository(
        settings, motor_client, sync_client
    )
    story_video_repo = build_story_video_repository(
        settings, motor_client, sync_client
    )
    telegram_access_repo = build_telegram_access_repository(settings, sync_client)
    dream_asset_service = DreamAssetService(dream_asset_repo)

    obs_repo = None
    obs_service = None
    dev_usage_ledger_repo = None
    if settings.dev_debug_ui_enabled:
        obs_repo, obs_service = build_observability(settings, motor_client, sync_client)
        dev_usage_ledger_repo = build_dev_usage_ledger_repository(
            settings, sync_client
        )

    openai_chat = OpenAIChatService(
        settings.openai_api_key,
        settings.openai_model,
        proxy_url=settings.openai_proxy_url,
    )
    video_job_service = VideoJobService(video_job_repo, settings)
    user_asset_context = UserAssetContextService(
        dream_asset_repo,
        user_profile_repo,
        generated_frame_repo,
        generated_image_repo,
        video_job_repo,
    )
    dream_pipeline = DreamPipelineService(
        settings,
        dream_run_repo=dream_run_repo,
        dream_scene_repo=dream_scene_repo,
        frame_repo=generated_frame_repo,
        scene_video_repo=scene_video_repo,
        story_repo=story_video_repo,
        dream_asset_repo=dream_asset_repo,
        user_profile_repo=user_profile_repo,
        user_context=user_asset_context,
        video_jobs=video_job_service,
        openai=openai_chat,
        observability=obs_service,
        generated_image_repo=generated_image_repo,
    )
    chat_orchestrator = ChatOrchestrator(
        settings,
        chat_store,
        openai_chat,
        observability=obs_service,
        dream_asset_repo=dream_asset_repo,
        user_profile_repo=user_profile_repo,
        generated_image_repo=generated_image_repo,
        dream_pipeline_service=dream_pipeline,
        dream_lite_run_repo=dream_lite_run_repo,
    )
    message_service = MessageService(
        repository,
        obs_service,
        chat_orchestrator=chat_orchestrator,
        dream_pipeline=dream_pipeline,
    )

    user_data_service = UserDataService(
        repository,
        chat_store,
        generated_image_repo,
        generated_frame_repo,
        story_video_repo,
        dream_asset_repo,
        user_profile_repo,
        dream_run_repo,
        dream_scene_repo,
        scene_video_repo,
        video_job_repo,
        observability_repo=obs_repo,
    )
    user_menu_router.message.middleware(UserDataServiceMiddleware(user_data_service))

    dream_lite_telegram_router.message.middleware(
        DreamLiteResourcesMiddleware(
            dream_lite_run_repo=dream_lite_run_repo,
            dream_pipeline=dream_pipeline,
            dream_lite_summary_repo=dream_lite_summary_repo,
            dream_lite_asset_repo=dream_lite_asset_repo,
        ),
    )
    dream_lite_telegram_router.callback_query.middleware(
        DreamLiteResourcesMiddleware(
            dream_lite_run_repo=dream_lite_run_repo,
            dream_pipeline=dream_pipeline,
            dream_lite_summary_repo=dream_lite_summary_repo,
            dream_lite_asset_repo=dream_lite_asset_repo,
        ),
    )

    bot = create_telegram_bot(settings)
    dp = Dispatcher()
    dp.update.middleware(
        TelegramAccessMiddleware(
            settings,
            access_repo=telegram_access_repo,
        )
    )
    dp.update.middleware(MessageServiceMiddleware(message_service))
    dp.include_router(user_menu_router)
    dp.include_router(media_log_router)
    dp.include_router(dream_lite_telegram_router)
    dp.include_router(telegram_router)
    dp.include_router(create_dream_asset_router(dream_asset_service))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        coll = motor_client[settings.mongodb_db][settings.mongodb_collection_messages]
        await ensure_indexes(coll)
        db = settings.mongodb_db
        await ensure_chat_indexes(
            motor_client[db][settings.mongodb_collection_conversation_messages],
            motor_client[db][settings.mongodb_collection_model_calls],
            motor_client[db][settings.mongodb_collection_tool_calls],
        )
        await ensure_dream_asset_indexes(
            motor_client[db][settings.mongodb_collection_dream_assets],
        )
        await ensure_user_profile_indexes(
            motor_client[db][settings.mongodb_collection_user_profiles],
        )
        await ensure_generated_image_indexes(
            motor_client[db][settings.mongodb_collection_generated_images],
        )
        await ensure_video_job_indexes(
            motor_client[db][settings.mongodb_collection_video_jobs],
        )
        try:
            resumed = video_job_service.resume_stale_pollers()
            if resumed:
                logger.info(
                    "Возобновлён фоновый опрос Wan для %s незавершённых video job(s) "
                    "(после рестарта uvicorn опрос в памяти обнуляется — см. VIDEO_JOB_MAX_POLL_SEC)",
                    resumed,
                )
        except Exception:
            logger.exception("Не удалось возобновить опрос video jobs при старте")
        await ensure_generated_frame_indexes(
            motor_client[db][settings.mongodb_collection_generated_frames],
        )
        await ensure_dream_run_indexes(
            motor_client[db][settings.mongodb_collection_dream_runs],
        )
        await ensure_dream_lite_run_indexes(
            motor_client[db][settings.mongodb_collection_dream_lite_runs],
        )
        await ensure_dream_lite_profile_indexes(
            motor_client[db][settings.mongodb_collection_dream_lite_profiles],
        )
        await ensure_dream_lite_artifact_indexes(
            motor_client[db][settings.mongodb_collection_dream_lite_artifacts],
        )
        await ensure_dream_lite_summary_indexes(
            motor_client[db][settings.mongodb_collection_dream_lite_summaries],
        )
        await ensure_dream_lite_asset_indexes(
            motor_client[db][settings.mongodb_collection_dream_lite_assets],
        )
        await ensure_dream_scene_indexes(
            motor_client[db][settings.mongodb_collection_dream_scenes],
        )
        await ensure_scene_video_indexes(
            motor_client[db][settings.mongodb_collection_scene_videos],
        )
        await ensure_story_video_indexes(
            motor_client[db][settings.mongodb_collection_story_videos],
        )
        if settings.dev_debug_ui_enabled:
            ocoll = motor_client[settings.mongodb_db][
                settings.mongodb_collection_observability
            ]
            await ensure_observability_indexes(ocoll)
            ensure_dev_usage_ledger_indexes(
                sync_client[settings.mongodb_db][
                    settings.mongodb_collection_dev_usage
                ]
            )
            ensure_dream_lite_step3_snapshot_indexes(
                sync_client[settings.mongodb_db]["dream_lite_step3_snapshots"]
            )

        async def _after_server_listening() -> None:
            # Планируется до yield, но выполнится после первого await внутри неё — когда event loop
            # обработает задачу, lifespan уже вышел из __aenter__ и uvicorn слушает PORT (cloudflared может подключиться).
            runtime_tunnel_file = settings.data_dir / "runtime" / "current_tunnel.txt"
            run_cf = settings.should_start_embedded_cloudflare_tunnel()
            if run_cf:
                local_target = f"http://127.0.0.1:{settings.port}"
                logger.info(
                    "Запуск Cloudflare quick tunnel (cloudflared) → %s",
                    local_target,
                )
                started = start_cloudflare_tunnel_background(
                    local_target,
                    runtime_file=runtime_tunnel_file,
                    cloudflared_bin=settings.cloudflared_bin,
                )
                if started:
                    got_url = await wait_for_cloudflare_tunnel_url(
                        settings.cloudflare_tunnel_timeout_sec,
                    )
                    if got_url:
                        logger.info(
                            "Публичный URL туннеля готов для webhook: %s",
                            get_current_tunnel_url(),
                        )
                    else:
                        logger.error(
                            "Cloudflare tunnel URL не получен за %.1f с; "
                            "увеличьте CLOUDFLARE_TUNNEL_TIMEOUT_SEC или задайте TELEGRAM_WEBHOOK_URL / PUBLIC_BASE_URL",
                            settings.cloudflare_tunnel_timeout_sec,
                        )
            else:
                if not settings.embed_cloudflare_tunnel_in_process:
                    logger.info(
                        "Встроенный cloudflared отключён (EMBED_CLOUDFLARE_TUNNEL=false). "
                        "Ожидается отдельный процесс: python run_cloudflared_tunnel.py "
                        "и URL в data/runtime/current_tunnel.txt.",
                    )
                else:
                    logger.info(
                        "Cloudflare quick tunnel пропущен: задайте START_CLOUDFLARE_TUNNEL=true "
                        "или SET_WEBHOOK_ON_STARTUP=true без TELEGRAM_WEBHOOK_URL и PUBLIC_BASE_URL.",
                    )

            if (
                settings.set_webhook_on_startup
                and not settings.embed_cloudflare_tunnel_in_process
                and settings.should_run_cloudflare_quick_tunnel()
            ):
                got_file = await wait_for_persisted_tunnel_base_url(
                    runtime_tunnel_file,
                    settings.cloudflare_tunnel_timeout_sec,
                )
                if got_file:
                    logger.info(
                        "Публичный URL из файла туннеля: %s",
                        read_persisted_tunnel_base_url(runtime_tunnel_file),
                    )
                else:
                    logger.error(
                        "Нет URL в %s — сначала запустите в другом терминале: python run_cloudflared_tunnel.py",
                        runtime_tunnel_file,
                    )

            if settings.set_webhook_on_startup:
                logger.info(
                    "Шаг: автоматический setWebhook (SET_WEBHOOK_ON_STARTUP=true) "
                    "после готовности туннеля/URL — см. логи bot.webhook_management",
                )
                try:
                    await set_webhook_from_settings(bot, settings)
                except ValueError as exc:
                    logger.error(
                        "Авто setWebhook пропущен: не удалось собрать URL. %s",
                        exc,
                    )

        startup_task = asyncio.create_task(_after_server_listening())

        print_local_app_banner(settings)
        schedule_open_gradio_in_browser(settings)
        yield
        try:
            await startup_task
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка фоновой настройки (Cloudflare tunnel / setWebhook)")
        await bot.session.close()
        stop_cloudflare_tunnel()
        motor_client.close()
        sync_client.close()

    app = FastAPI(title="Dream Viz API", lifespan=lifespan)
    register_telegram_webhook(app, bot, dp, settings, observability=obs_service)
    app.include_router(build_dream_lite_montage_json_router(dream_pipeline))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    gradio_app = build_gradio_app(repository, settings)
    # root_path в mount_gradio_app задаёт blocks.root_path и ломает маршруты, если nginx
    # проксирует уже «обрезанный» путь (/ui). Публичный префикс — GRADIO_PROXY_PREFIX / заголовки nginx.
    gr.mount_gradio_app(app, gradio_app, path=settings.gradio_mount_path, root_path=None)

    app.include_router(create_prompts_editor_router(settings))

    if settings.dev_debug_ui_enabled and obs_repo is not None:
        from ui.dev.router import (
            create_dev_console_router,
            create_legacy_debug_redirect_router,
            mount_dev_static,
        )

        app.include_router(
            create_dev_console_router(
                settings,
                repository,
                obs_repo,
                chat_store,
                dream_asset_repo,
                video_job_repo,
                dream_run_repo=dream_run_repo,
                dream_scene_repo=dream_scene_repo,
                generated_frame_repo=generated_frame_repo,
                generated_image_repo=generated_image_repo,
                scene_video_repo=scene_video_repo,
                story_video_repo=story_video_repo,
                dream_pipeline_service=dream_pipeline,
                dev_usage_ledger_repo=dev_usage_ledger_repo,
                dream_lite_run_repo=dream_lite_run_repo,
                dream_lite_artifact_repo=dream_lite_artifact_repo,
                telegram_access_repo=telegram_access_repo,
                dream_lite_step3_snapshot_repo=dream_lite_step3_snapshot_repo,
            ),
        )
        app.include_router(create_legacy_debug_redirect_router(settings))
        mount_dev_static(app)

    return app
