"""Загрузка настроек из файла(ов) в корне проекта."""
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _apply_project_env_files_to_os() -> None:
    """
    Подмешивает переменные из файлов корня проекта в os.environ с override=True.

    У pydantic-settings переменные **среды ОС** обычно сильнее, чем `env_file`.
    Из‑за этого старый OPENAI_API_KEY в системных/User env Windows мог перекрывать
    значение из локального `env`. Явная загрузка dotenv с override даёт приоритет файлам проекта.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for name in ("ENV", "env", ".env"):
        path = _PROJECT_ROOT / name
        if path.is_file():
            load_dotenv(path, override=True)


_apply_project_env_files_to_os()


class Settings(BaseSettings):
    """Конфигурация приложения. Значения из `ENV` / `env` / `.env` в корне (после подмешивания в os.environ)."""

    model_config = SettingsConfigDict(
        env_file=(
            _PROJECT_ROOT / "ENV",
            _PROJECT_ROOT / "env",
            _PROJECT_ROOT / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., description="Токен бота от @BotFather")
    telegram_webhook_secret: str | None = Field(
        default=None,
        description="Секрет для webhook (Telegram: secret_token)",
    )
    telegram_proxy_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_PROXY_URL"),
        description="SOCKS5/HTTP proxy URL только для Telegram Bot API (пример: socks5h://user:pass@host:port)",
    )

    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_db: str = Field(default="dream_viz")
    mongodb_collection_messages: str = Field(
        default="inbound_messages",
        validation_alias=AliasChoices(
            "MONGODB_COLLECTION_MESSAGES",
            "MONGODB_COLLECTION",
        ),
        description="Коллекция для входящих сообщений (алиас MONGODB_COLLECTION для совместимости)",
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    webhook_path: str = Field(
        default="/webhook",
        description="Путь на FastAPI, куда Telegram шлёт POST (локально + тот же путь на публичном URL)",
    )
    gradio_mount_path: str = Field(default="/ui")
    dev_debug_ui_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEV_DEBUG_UI", "DEBUG_CONSOLE"),
        description="Локальная dev-консоль /dev (доступ только с localhost)",
    )
    mongodb_collection_observability: str = Field(
        default="observability_events",
        description="Коллекция событий observability для dev UI",
    )
    mongodb_collection_dream_assets: str = Field(
        default="dream_assets",
        description="Визуальные материалы пользователя (Telegram file_id + классификация)",
    )
    mongodb_collection_user_profiles: str = Field(
        default="user_profiles",
        description="Профиль пользователя: base_character_asset_id, флаги онбординга",
    )
    mongodb_collection_generated_images: str = Field(
        default="generated_images",
        description="Скрытый журнал сгенерированных кадров (video pipeline)",
    )
    mongodb_collection_generated_frames: str = Field(
        default="generated_frames",
        description="Кадры сцен пайплайна сон→видео (dream orchestrator)",
    )
    mongodb_collection_dream_runs: str = Field(
        default="dream_runs",
        description="Запуски dream-to-story-video (статус, план сцен, ошибки)",
    )
    mongodb_collection_dream_scenes: str = Field(
        default="dream_scenes",
        description="Сцены плана LLM для dream pipeline (пошаговый UI)",
    )
    mongodb_collection_scene_videos: str = Field(
        default="scene_videos",
        description="Wan-анимация по сцене (промпты, job, URL) для dev UI",
    )
    mongodb_collection_story_videos: str = Field(
        default="story_videos",
        description="Итоговые склеенные ролики пайплайна сна",
    )

    telegram_webhook_url: str | None = Field(
        default=None,
        description="Полный HTTPS URL webhook для setWebhook (например https://xxx.ngrok-free.app/webhook)",
    )
    public_base_url: str | None = Field(
        default=None,
        description="Базовый публичный HTTPS URL без слэша; итоговый webhook = PUBLIC_BASE_URL + WEBHOOK_PATH",
    )
    set_webhook_on_startup: bool = Field(default=False)

    start_ngrok_tunnel: bool = Field(
        default=False,
        validation_alias=AliasChoices("START_NGROK_TUNNEL", "AUTO_TUNNEL"),
        description="Запускать ngrok вместе с main.py и выставлять webhook автоматически",
    )
    ngrok_auth_token: str | None = Field(
        default=None,
        validation_alias="NGROK_AUTH_TOKEN",
        description="Токен ngrok (dashboard → Your Authtoken)",
    )

    start_cloudflare_tunnel: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "START_CLOUDFLARE_TUNNEL",
            "AUTO_CLOUDFLARE_TUNNEL",
        ),
        description="Запускать cloudflared quick tunnel при старте FastAPI и брать публичный URL из логов",
    )
    cloudflare_tunnel_timeout_sec: float = Field(
        default=60.0,
        ge=1.0,
        le=120.0,
        description="Сколько секунд ждать строку с trycloudflare.com (cloudflared часто печатает URL с задержкой)",
    )
    cloudflared_bin: str | None = Field(
        default=None,
        validation_alias="CLOUDFLARED_BIN",
        description="Полный путь к cloudflared.exe (надёжнее PATH при фиктивном 0-байтном cloudflared в System32)",
    )
    embed_cloudflare_tunnel_in_process: bool = Field(
        default=False,
        validation_alias="EMBED_CLOUDFLARE_TUNNEL",
        description="False (по умолчанию): туннель только run_cloudflared_tunnel.py → data/runtime/current_tunnel.txt. True: cloudflared внутри main.py",
    )

    local_ui_host: str = Field(
        default="127.0.0.1",
        description="Хост для ссылки в браузере (не меняйте bind uvicorn)",
    )
    open_browser_on_start: bool = Field(
        default=True,
        description="Открыть Gradio в браузере после старта сервера",
    )
    browser_open_delay_sec: float = Field(
        default=1.0,
        ge=0.0,
        le=30.0,
        description="Задержка перед открытием вкладки (сек), пока поднимется uvicorn",
    )

    data_dir: Path = Field(
        default_factory=lambda: _PROJECT_ROOT / "data",
        description="Корень для логов, временных файлов и артефактов пайплайна",
    )

    dashscope_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHSCOPE_API_KEY"),
        description="Alibaba DashScope / Qwen Image (также можно задать в env-файле)",
    )
    dashscope_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHSCOPE_ENDPOINT"),
        description="URL multimodal-generation; по умолчанию international endpoint в клиенте",
    )

    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY"),
        description="Ключ OpenAI для чата и tool calling",
    )
    openai_proxy_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_PROXY_URL"),
        description="SOCKS5/HTTP proxy URL только для OpenAI клиента (пример: socks5h://user:pass@host:port)",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL"),
        description="Модель чата (Chat Completions)",
    )

    mongodb_collection_conversation_messages: str = Field(
        default="conversation_messages",
        description="История диалога для агента",
    )
    mongodb_collection_model_calls: str = Field(
        default="model_calls",
        description="Лог запросов к OpenAI (для dev UI)",
    )
    mongodb_collection_tool_calls: str = Field(
        default="tool_calls",
        description="Лог вызовов tools (для dev UI)",
    )
    mongodb_collection_video_jobs: str = Field(
        default="video_jobs",
        description="Асинхронные задачи image-to-video (Wan / DashScope)",
    )

    dashscope_video_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHSCOPE_VIDEO_ENDPOINT"),
        description=(
            "POST URL video-synthesis; по умолчанию Singapore intl. "
            "GET /tasks/{id} выводится из того же хоста."
        ),
    )

    def should_run_cloudflare_quick_tunnel(self) -> bool:
        """
        Запускать cloudflared, если явно включено или нужен публичный URL для setWebhook без env.

        True, если START_CLOUDFLARE_TUNNEL=true, либо SET_WEBHOOK_ON_STARTUP=true и при этом
        не заданы TELEGRAM_WEBHOOK_URL и PUBLIC_BASE_URL (локальная разработка без ручной вставки URL).
        """
        if self.start_cloudflare_tunnel:
            return True
        if not self.set_webhook_on_startup:
            return False
        has_manual = bool(
            (self.telegram_webhook_url or "").strip()
            or (self.public_base_url or "").strip()
        )
        return not has_manual

    def should_start_embedded_cloudflare_tunnel(self) -> bool:
        """Запускать subprocess cloudflared внутри uvicorn (не отдельный скрипт)."""
        if not self.embed_cloudflare_tunnel_in_process:
            return False
        return self.should_run_cloudflare_quick_tunnel()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """Для тестов: сброс кэша get_settings."""
    get_settings.cache_clear()
