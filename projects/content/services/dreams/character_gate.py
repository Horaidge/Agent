"""Создание базового персонажа для dream pipeline (без дублирования ChatOrchestrator)."""
from __future__ import annotations

import logging
import re
from typing import Any

from services.assets.dream_asset_service import ASSET_TYPE_CHARACTER, STATUS_GENERATED
from services.tools.image_tools import tool_generate_base_character
from storage.dream_asset_repository import DreamAssetRepository
from storage.user_profile_repository import UserProfileRepository

logger = logging.getLogger(__name__)

# Пользователь явно не хочет своё лицо — сразу нейтральный персонаж.
# Важно: не матчить голое «без» — оно есть почти в любом русском тексте («без сна», «без двери»).
_OPT_OUT_FACE = re.compile(
    r"(?:^|[\s,.])(?:анон|anon)(?:$|[\s,.])"
    r"|аноним"
    r"|без\s+лица"
    r"|не\s+мо[её]\s+лицо"
    r"|не\s+хочу\s+сво[ейё]?\s+лиц"
    r"|не\s+нужно\s+лиц"
    r"|чужой\s+герой",
    re.IGNORECASE | re.UNICODE,
)


def user_declines_own_face(dream_text: str) -> bool:
    return bool(_OPT_OUT_FACE.search(dream_text or ""))


async def create_base_character_and_profile(
    *,
    user_id: int,
    chat_id: int,
    source_message_id: int,
    appearance: str | None,
    dream_repo: DreamAssetRepository,
    user_profile_repo: UserProfileRepository,
) -> tuple[str, str]:
    """
    Генерирует базового персонажа, пишет dream_assets + user_profiles.
    Возвращает (asset_id, character_uuid).
    """
    bc = tool_generate_base_character(appearance)
    if not bc.ok or not bc.image_url:
        raise RuntimeError(bc.error or "Qwen base character failed")

    doc: dict[str, Any] = {
        "owner_user_id": user_id,
        "telegram_user_id": user_id,
        "chat_id": chat_id,
        "telegram_file_id": None,
        "source_message_id": source_message_id,
        "asset_type": ASSET_TYPE_CHARACTER,
        "status": STATUS_GENERATED,
        "is_base_character": True,
        "source_image_url": bc.image_url,
        "character_uuid": bc.character_id,
        "prompt_used": bc.prompt_used,
    }
    asset_id = await dream_repo.insert_one(doc)
    await user_profile_repo.set_base_character_asset(user_id, asset_id=asset_id)
    logger.info("character_gate: base character asset_id=%s user=%s", asset_id, user_id)
    return asset_id, bc.character_id
