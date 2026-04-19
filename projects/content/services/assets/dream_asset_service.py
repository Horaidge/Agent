"""Визуальные материалы пользователя (dream_assets): создание и классификация."""
from __future__ import annotations

from typing import Any

from storage.dream_asset_repository import DreamAssetRepository

# Значения в MongoDB
ASSET_TYPE_FACE = "face"
ASSET_TYPE_ENVIRONMENT = "environment"
ASSET_TYPE_DREAM_OBJECT = "dream_object"
ASSET_TYPE_CHARACTER = "character"
ASSET_TYPE_OTHER = "other"

STATUS_PENDING = "pending_classification"
STATUS_CLASSIFIED = "classified"
STATUS_GENERATED = "generated"

# Подписи для пользователя и dev UI
ASSET_TYPE_LABELS: dict[str, str] = {
    ASSET_TYPE_FACE: "Моё лицо",
    ASSET_TYPE_ENVIRONMENT: "Окружение",
    ASSET_TYPE_DREAM_OBJECT: "Объект сна",
    ASSET_TYPE_CHARACTER: "Персонаж",
    ASSET_TYPE_OTHER: "Другое",
}


class DreamAssetService:
    def __init__(self, repo: DreamAssetRepository) -> None:
        self._repo = repo

    async def create_pending_asset(
        self,
        *,
        owner_user_id: int,
        telegram_user_id: int,
        chat_id: int,
        telegram_file_id: str,
        source_message_id: int,
    ) -> str:
        doc = {
            "owner_user_id": owner_user_id,
            "telegram_user_id": telegram_user_id,
            "chat_id": chat_id,
            "telegram_file_id": telegram_file_id,
            "source_message_id": source_message_id,
            "asset_type": None,
            "status": STATUS_PENDING,
        }
        return await self._repo.insert_one(doc)

    async def set_asset_type(
        self,
        asset_id: str,
        *,
        owner_user_id: int,
        asset_type: str,
    ) -> bool:
        if asset_type not in ASSET_TYPE_LABELS:
            return False
        return await self._repo.update_classification(
            asset_id,
            owner_user_id=owner_user_id,
            asset_type=asset_type,
            status=STATUS_CLASSIFIED,
        )

    async def get_user_assets(self, owner_user_id: int) -> list[dict[str, Any]]:
        return await self._repo.list_by_owner(owner_user_id)

    async def get_asset_by_id(self, asset_id: str) -> dict[str, Any] | None:
        return await self._repo.find_by_id(asset_id)
