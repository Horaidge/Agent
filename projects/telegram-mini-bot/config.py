from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
for name in ("ENV", "env", ".env"):
    path = ROOT / name
    if path.is_file():
        load_dotenv(path, override=True)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    openai_model: str
    openai_proxy_url: str | None
    public_site_url: str
    admin_user_ids: str
    prompts_dir: Path
    data_dir: Path
    supabase_url: str
    supabase_service_role_key: str
    supabase_rag_table: str
    openai_embedding_model: str
    rag_top_k: int
    rag_disabled: bool
    dream_lite_enabled: bool
    content_project_root: Path
    mongodb_uri: str
    mongodb_db: str
    public_base_url: str

    def admin_ids(self) -> set[int]:
        raw = (self.admin_user_ids or "").strip()
        if not raw:
            return set()
        return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}

    def may_edit_prompt(self, user_id: int) -> bool:
        allowed = self.admin_ids()
        if not allowed:
            return True
        return user_id in allowed

    def rag_enabled(self) -> bool:
        if self.rag_disabled:
            return False
        return bool(self.supabase_url.strip() and self.supabase_service_role_key.strip())


@lru_cache
def get_settings() -> Settings:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not token:
        raise RuntimeError("Задайте TELEGRAM_BOT_TOKEN в telegram-mini-bot/.env")
    if not api_key:
        raise RuntimeError("Задайте OPENAI_API_KEY в telegram-mini-bot/.env")
    rag_raw = (os.environ.get("RAG_DISABLED") or "").strip().lower()
    rag_disabled = rag_raw in ("1", "true", "yes", "on")
    rag_k = int((os.environ.get("RAG_TOP_K") or "10").strip() or "10")
    rag_k = max(1, min(rag_k, 50))
    return Settings(
        telegram_bot_token=token,
        openai_api_key=api_key,
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-5.5").strip() or "gpt-5.5",
        openai_proxy_url=(os.environ.get("OPENAI_PROXY_URL") or "").strip() or None,
        public_site_url=os.environ.get("PUBLIC_SITE_URL", "https://smartagentplatform.ru").strip(),
        admin_user_ids=os.environ.get("ADMIN_USER_IDS", "").strip(),
        prompts_dir=ROOT / "prompts",
        data_dir=ROOT / "data",
        supabase_url=(os.environ.get("SUPABASE_URL") or "").strip(),
        supabase_service_role_key=(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip(),
        supabase_rag_table=(os.environ.get("SUPABASE_RAG_TABLE") or "telegram_rag_chunks").strip()
        or "telegram_rag_chunks",
        openai_embedding_model=(
            os.environ.get("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
        ).strip()
        or "text-embedding-3-small",
        rag_top_k=rag_k,
        rag_disabled=rag_disabled,
        dream_lite_enabled=(os.environ.get("DREAM_LITE_ENABLED") or "").strip().lower()
        in ("1", "true", "yes", "on"),
        content_project_root=Path(
            (os.environ.get("CONTENT_PROJECT_ROOT") or str(ROOT.parent / "content")).strip()
        ),
        mongodb_uri=(os.environ.get("MONGODB_URI") or "").strip(),
        mongodb_db=(os.environ.get("MONGODB_DB") or "dream_viz").strip() or "dream_viz",
        public_base_url=(
            os.environ.get("PUBLIC_BASE_URL")
            or os.environ.get("PUBLIC_SITE_URL", "https://smartagentplatform.ru")
        ).strip(),
    )
