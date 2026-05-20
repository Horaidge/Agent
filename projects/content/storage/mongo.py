"""Фабрики клиентов MongoDB (Motor + PyMongo) и репозитория."""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

from core.config.settings import Settings
from core.observability.repository import ObservabilityRepository
from core.observability.service import ObservabilityService
from storage.chat_repository import ChatStoreRepository
from storage.dream_asset_repository import DreamAssetRepository
from storage.dream_lite_artifact_repository import DreamLiteArtifactRepository
from storage.dream_lite_asset_repository import DreamLiteAssetRepository
from storage.dream_lite_run_repository import DreamLiteRunRepository
from storage.dream_lite_step3_snapshot_repository import DreamLiteStep3SnapshotRepository
from storage.dream_lite_summary_repository import DreamLiteSummaryRepository
from storage.dream_run_repository import DreamRunRepository
from storage.dream_scene_repository import DreamSceneRepository
from storage.generated_frame_repository import GeneratedFrameRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.repository import MessageRepository
from storage.scene_video_repository import SceneVideoRepository
from storage.story_video_repository import StoryVideoRepository
from storage.telegram_access_repository import TelegramAccessRepository
from storage.user_profile_repository import UserProfileRepository
from storage.dev_usage_ledger_repository import DevUsageLedgerRepository
from storage.video_job_repository import VideoJobRepository


def build_message_repository(settings: Settings) -> tuple[
    AsyncIOMotorClient,
    MongoClient,
    MessageRepository,
]:
    motor_client = AsyncIOMotorClient(settings.mongodb_uri)
    sync_client = MongoClient(settings.mongodb_uri)

    async_coll = motor_client[settings.mongodb_db][settings.mongodb_collection_messages]
    sync_coll = sync_client[settings.mongodb_db][settings.mongodb_collection_messages]

    repo = MessageRepository(async_coll, sync_coll)
    return motor_client, sync_client, repo


def build_chat_store(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> ChatStoreRepository:
    db = settings.mongodb_db
    conv_a = motor_client[db][settings.mongodb_collection_conversation_messages]
    conv_s = sync_client[db][settings.mongodb_collection_conversation_messages]
    model_a = motor_client[db][settings.mongodb_collection_model_calls]
    model_s = sync_client[db][settings.mongodb_collection_model_calls]
    tool_a = motor_client[db][settings.mongodb_collection_tool_calls]
    tool_s = sync_client[db][settings.mongodb_collection_tool_calls]
    return ChatStoreRepository(conv_a, conv_s, model_a, model_s, tool_a, tool_s)


def build_dream_asset_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> DreamAssetRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_dream_assets
    return DreamAssetRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_video_job_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> VideoJobRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_video_jobs
    return VideoJobRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_dev_usage_ledger_repository(
    settings: Settings,
    sync_client: MongoClient,
) -> DevUsageLedgerRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_dev_usage
    return DevUsageLedgerRepository(sync_client[db][name])


def build_user_profile_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> UserProfileRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_user_profiles
    return UserProfileRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_generated_image_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> GeneratedImageRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_generated_images
    return GeneratedImageRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_generated_frame_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> GeneratedFrameRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_generated_frames
    return GeneratedFrameRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_dream_run_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> DreamRunRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_dream_runs
    return DreamRunRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_dream_lite_run_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> DreamLiteRunRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_dream_lite_runs
    profile_name = settings.mongodb_collection_dream_lite_profiles
    return DreamLiteRunRepository(
        motor_client[db][name],
        sync_client[db][name],
        motor_client[db][profile_name],
        sync_client[db][profile_name],
    )


def build_dream_lite_artifact_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> DreamLiteArtifactRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_dream_lite_artifacts
    return DreamLiteArtifactRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_dream_lite_summary_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> DreamLiteSummaryRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_dream_lite_summaries
    return DreamLiteSummaryRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_dream_lite_asset_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> DreamLiteAssetRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_dream_lite_assets
    return DreamLiteAssetRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_dream_lite_step3_snapshot_repository(
    settings: Settings,
    sync_client: MongoClient,
) -> DreamLiteStep3SnapshotRepository:
    db = settings.mongodb_db
    return DreamLiteStep3SnapshotRepository(sync_client[db]["dream_lite_step3_snapshots"])


def build_dream_scene_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> DreamSceneRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_dream_scenes
    return DreamSceneRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_scene_video_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> SceneVideoRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_scene_videos
    return SceneVideoRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_story_video_repository(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> StoryVideoRepository:
    db = settings.mongodb_db
    name = settings.mongodb_collection_story_videos
    return StoryVideoRepository(
        motor_client[db][name],
        sync_client[db][name],
    )


def build_telegram_access_repository(
    settings: Settings,
    sync_client: MongoClient,
) -> TelegramAccessRepository:
    db = settings.mongodb_db
    return TelegramAccessRepository(sync_client[db]["telegram_access_control"])


def build_observability(
    settings: Settings,
    motor_client: AsyncIOMotorClient,
    sync_client: MongoClient,
) -> tuple[ObservabilityRepository, ObservabilityService]:
    ac = motor_client[settings.mongodb_db][settings.mongodb_collection_observability]
    sc = sync_client[settings.mongodb_db][settings.mongodb_collection_observability]
    orepo = ObservabilityRepository(ac, sc)
    return orepo, ObservabilityService(orepo)
