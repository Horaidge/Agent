"""Загрузка настроек из файла(ов) в корне проекта."""
from functools import lru_cache
import os
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


def detach_gradio_root_path_env() -> None:
    """
    Gradio читает ``GRADIO_ROOT_PATH`` из ``os.environ`` при создании ``gr.Blocks()`` и
    смешивает его с mount на ``/ui``. За nginx с ``location /content/`` бэкенд получает
    путь ``/ui``, а не ``/content/ui`` — из‑за несовпадения отдаётся 404.

    Храним публичный префикс в ``GRADIO_PROXY_PREFIX`` (и в Settings.gradio_root_path);
    имя ``GRADIO_ROOT_PATH`` оставляем только для обратной совместимости: переносим в
    ``GRADIO_PROXY_PREFIX`` и убираем из окружения до ``import gradio``.
    """
    val = os.environ.pop("GRADIO_ROOT_PATH", None)
    if val is not None and "GRADIO_PROXY_PREFIX" not in os.environ:
        os.environ["GRADIO_PROXY_PREFIX"] = val


detach_gradio_root_path_env()


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
    telegram_access_allowlist_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("TELEGRAM_ACCESS_ALLOWLIST_ENABLED"),
        description="Включить ограничение Telegram-бота по allowlist user_id",
    )
    telegram_allowed_user_ids: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_ALLOWED_USER_IDS"),
        description="Список Telegram user_id через запятую для доступа к боту",
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
    gradio_root_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GRADIO_PROXY_PREFIX", "GRADIO_ROOT_PATH"),
        description=(
            "Публичный префикс UI за reverse proxy (напр. /content → https://домен/content/ui). "
            "Задавайте GRADIO_PROXY_PREFIX, не GRADIO_ROOT_PATH: последнее зарезервировано под "
            "внутреннее поведение Gradio и переносится в GRADIO_PROXY_PREFIX при старте."
        ),
    )
    dev_debug_ui_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEV_DEBUG_UI", "DEBUG_CONSOLE"),
        description="Локальная dev-консоль /dev (доступ только с localhost)",
    )
    dev_debug_ui_allow_remote: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEV_DEBUG_UI_ALLOW_REMOTE"),
        description="Разрешить доступ к /dev не только с localhost (например, через tunnel)",
    )
    dev_debug_ui_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEV_DEBUG_UI_USERNAME"),
        description="Логин Basic Auth для /dev (если задан, доступ только с логином/паролем)",
    )
    dev_debug_ui_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEV_DEBUG_UI_PASSWORD"),
        description="Пароль Basic Auth для /dev",
    )
    uvicorn_reload: bool = Field(
        default=False,
        validation_alias=AliasChoices("UVICORN_RELOAD"),
        description="Автоперезапуск uvicorn при изменении файлов (только локальная разработка)",
    )
    prompts_editor_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PROMPTS_EDITOR_SECRET"),
        description="Секрет Bearer для API редактирования prompts (GET/PUT /api/prompts/*); фронт проксирует через Next",
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
    mongodb_collection_dream_lite_runs: str = Field(
        default="dream_lite_runs",
        description="Dream Pipeline Lite: пошаговый run (user_id + lite_run_id), без смешивания пользователей",
    )
    mongodb_collection_dream_lite_profiles: str = Field(
        default="dream_lite_profiles",
        description="Dream Pipeline Lite: эталонные профили конфигурации шагов; active профиль применяется к новым run",
    )
    mongodb_collection_dream_lite_artifacts: str = Field(
        default="dream_lite_artifacts",
        description="Dream Pipeline Lite: метаданные сохранённых кадров (/dev/static/), TTL ~2 суток",
    )
    mongodb_collection_dream_lite_summaries: str = Field(
        default="dream_lite_run_summaries",
        description="Dream Pipeline Lite: лёгкая проекция run для истории Telegram/UX",
    )
    mongodb_collection_dream_lite_assets: str = Field(
        default="dream_lite_assets",
        description="Dream Pipeline Lite: канонический реестр медиа (env/char/frame/clip/final_video)",
    )
    dream_lite_retention_days: int = Field(
        default=30,
        ge=1,
        le=3650,
        description="Сколько дней хранить run/summary/assets до архивации/очистки",
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

    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY"),
        description="Ключ OpenRouter (генерация изображений Сборщиком; только env, без хардкода)",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("OPENROUTER_BASE_URL"),
        description="База API OpenRouter (chat/completions)",
    )
    openrouter_image_model: str = Field(
        default="google/gemini-2.5-flash-image",
        validation_alias=AliasChoices("OPENROUTER_IMAGE_MODEL"),
        description="Id модели с output image (см. каталог OpenRouter)",
    )
    openrouter_image_model_fallback: str = Field(
        default="google/gemini-3.1-flash-image-preview",
        validation_alias=AliasChoices("OPENROUTER_IMAGE_MODEL_FALLBACK"),
        description=(
            "Вторая модель после основной; затем цепочка только моделей с выходом image+text на OpenRouter "
            "(Gemini image, GPT image — см. код). Для Flux/Seedream задайте primary вручную в UI."
        ),
    )
    video_generation_backend: str = Field(
        default="dashscope",
        validation_alias=AliasChoices("VIDEO_GENERATION_BACKEND"),
        description=(
            "Источник image-to-video по умолчанию: dashscope (прямой Alibaba API) "
            "или openrouter (POST /api/v1/videos, напр. alibaba/wan-2.7)"
        ),
    )
    openrouter_video_model: str = Field(
        default="alibaba/wan-2.7",
        validation_alias=AliasChoices("OPENROUTER_VIDEO_MODEL"),
        description="Id модели видео на OpenRouter (WAN 2.7 и др.)",
    )
    openrouter_video_provider_json: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_VIDEO_PROVIDER_JSON"),
        description=(
            "Необязательный JSON для поля provider в OpenRouter Video API "
            '(маршрутизация провайдеров), напр. {"order": ["Alibaba"]}'
        ),
    )
    openrouter_http_referer: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_HTTP_REFERER"),
        description="Опционально HTTP-Referer для OpenRouter (рекомендации провайдера)",
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
        default="gpt-4.1-nano",
        validation_alias=AliasChoices("OPENAI_MODEL"),
        description="Модель чата и всех вызовов OpenAI, кроме Stage 0 dream (см. openai_model_dream_decompose)",
    )
    openai_model_dream_decompose: str = Field(
        default="gpt-4.1",
        validation_alias=AliasChoices("OPENAI_MODEL_DREAM_DECOMPOSE"),
        description=(
            "Модель по умолчанию только для Stage 0 dream (декомпозиция / раскадровка + motion). "
            "Один json_completion на run; image prompts и чат — openai_model (обычно gpt-4.1-nano)."
        ),
    )
    openai_dream_decompose_temperature: float | None = Field(
        default=0.0,
        validation_alias=AliasChoices("OPENAI_DREAM_DECOMPOSE_TEMPERATURE"),
        ge=0.0,
        le=2.0,
        description="Temperature только для Beat Planner / Stage 0 decompose. 0.0 повышает детерминизм.",
    )
    openai_dream_decompose_max_tokens: int | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_DREAM_DECOMPOSE_MAX_TOKENS"),
        ge=1,
        description="Лимит токенов для Beat Planner / Stage 0 decompose.",
    )
    openai_dream_decompose_seed: int | None = Field(
        default=42,
        validation_alias=AliasChoices("OPENAI_DREAM_DECOMPOSE_SEED"),
        description="Seed для Beat Planner / Stage 0 decompose (если поддерживается моделью).",
    )
    openai_dream_decompose_model_options: str = Field(
        default="gpt-4.1,gpt-4.1-mini,gpt-4.1-nano,gpt-4o,gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_DREAM_DECOMPOSE_MODEL_OPTIONS"),
        description=(
            "Допустимые id моделей для Stage 0 (через запятую): dev-форма, валидация override. "
            "Семейство GPT-4.1: полная / mini / nano; линейка 4o: gpt-4o и gpt-4o-mini."
        ),
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
    mongodb_collection_dev_usage: str = Field(
        default="dev_usage_ledger",
        description="Учёт токенов/вызовов dev Playground и API (персистентно в Mongo)",
    )
    mongodb_collection_video_jobs: str = Field(
        default="video_jobs",
        description="Асинхронные задачи image-to-video (Wan / DashScope)",
    )
    dream_lite_playground_user_id: int = Field(
        default=355777834,
        validation_alias=AliasChoices("DREAM_LITE_PLAYGROUND_USER_ID"),
        description="User ID для запусков Dream Lite из Dev Playground (для parity с Telegram)",
    )

    dashscope_video_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHSCOPE_VIDEO_ENDPOINT"),
        description=(
            "POST URL video-synthesis; по умолчанию Singapore intl. "
            "GET /tasks/{id} выводится из того же хоста."
        ),
    )

    def dream_decompose_model_options_list(self) -> list[str]:
        """Список моделей для выбора Stage 0 (dev) и проверки override."""
        parts = [
            p.strip()
            for p in (self.openai_dream_decompose_model_options or "").split(",")
        ]
        out = [p for p in parts if p]
        if not out:
            return [
                "gpt-4.1",
                "gpt-4.1-mini",
                "gpt-4.1-nano",
                "gpt-4o",
                "gpt-4o-mini",
            ]
        return out

    def resolve_dream_decompose_model(self, override: str | None) -> str:
        """Итоговая модель Stage 0: override из dev/run, иначе OPENAI_MODEL_DREAM_DECOMPOSE."""
        allow = set(self.dream_decompose_model_options_list())
        default = (self.openai_model_dream_decompose or "").strip() or (
            self.openai_model
        )
        if override is None or not str(override).strip():
            return default
        o = str(override).strip()
        if o in allow:
            return o
        return default

    def telegram_allowed_user_ids_set(self) -> set[int]:
        out: set[int] = set()
        for raw in (self.telegram_allowed_user_ids or "").split(","):
            token = raw.strip()
            if not token:
                continue
            try:
                out.add(int(token))
            except Exception:
                continue
        return out

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
