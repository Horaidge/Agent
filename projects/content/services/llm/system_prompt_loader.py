"""Загрузка системных промптов из markdown-файлов (без кеша — правки подхватываются сразу)."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Корень проекта: services/llm → services → корень (не зависит от текущей рабочей директории)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = _PROJECT_ROOT / "prompts"
# User-контракты режиссёра (фрагменты user-сообщения: схема JSON + правила), рядом с prompts/
CONTRACTS_DIR = _PROJECT_ROOT / "contracts"
# Единственный файл системного промпта для чат-агента (ChatOrchestrator → OpenAI)
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system_prompt.md"
# Дополнительный system-слой чата: сценарий «картинки → видео → склейка» и вызовы инструментов (редактируется отдельно)
CHAT_VIDEO_SCENARIO_TOOLS_FILE = PROMPTS_DIR / "chat_video_scenario_tools.md"
# Дополнительный слой system для всех вызовов OpenAI (чат, dream JSON и т.д.)
GLOBAL_MODEL_POLICY_FILE = PROMPTS_DIR / "global_model_policy.md"
# Planning layer · Beat Planner (dev 0A): header_context + beats. Пустой = встроенный дефолт в dream_scene_planner.
DREAM_BEAT_PLANNER_FILE = PROMPTS_DIR / "dream_beat_planner.md"
# Dream pipeline · шаг «сцены + motion» (production decompose_dream_scenes). Пустой = встроенный SYSTEM_DECOMPOSE в коде.
DREAM_SCENE_MOTION_DECOMPOSE_FILE = PROMPTS_DIR / "dream_scene_motion_decompose.md"
# Planning layer · Сценарист (dev 0B): beats → scenes. Не смешивать с Beat Planner и с motion-decompose.
DREAM_DECOMPOSITION_FILE = PROMPTS_DIR / "dream_decomposition.md"
# Шаг 2 Dream pipeline: промпты стартовых кадров (JSON). Пустой файл = встроенный дефолт в dream_scene_planner.
DREAM_IMAGE_PROMPTS_FILE = PROMPTS_DIR / "dream_image_prompts.md"
# Классификатор: запуск dream pipeline по свободному тексту (без /dream). Пустой = дефолт в dream_orchestrator.
DREAM_INTENT_ROUTING_FILE = PROMPTS_DIR / "dream_intent_routing.md"
# Playground · Режиссёр: два этапа (референсы → ключевые кадры)
DREAM_DIRECTOR_REFERENCES_FILE = PROMPTS_DIR / "dream_director_references.md"
DREAM_DIRECTOR_KEYFRAMES_FILE = PROMPTS_DIR / "dream_director_keyframes.md"
# Dev · Dream Pipeline Lite: два простых текстовых шага (окружения → кадры), без JSON-контрактов
DREAM_PIPELINE_LITE_ENVIRONMENTS_FILE = PROMPTS_DIR / "dream_pipeline_lite_environments.md"
DREAM_PIPELINE_LITE_ENVIRONMENTS_SIMPLE_FILE = (
    PROMPTS_DIR / "dream_pipeline_lite_environments_simple.md"
)
DREAM_PIPELINE_LITE_FRAMES_FILE = PROMPTS_DIR / "dream_pipeline_lite_frames.md"
DREAM_PIPELINE_LITE_FRAMES_PREV_LINK_FILE = (
    PROMPTS_DIR / "dream_pipeline_lite_frames_prev_link.md"
)
DREAM_PIPELINE_LITE_TRANSITIONS_FILE = PROMPTS_DIR / "dream_pipeline_lite_transitions.md"
DREAM_PIPELINE_LITE_TRANSITIONS_SEEDANCE_FILE = (
    PROMPTS_DIR / "dream_pipeline_lite_transitions_seedance.md"
)
DREAM_PIPELINE_LITE_TRANSITIONS_WAN26_FILE = (
    PROMPTS_DIR / "dream_pipeline_lite_transitions_wan26.md"
)
DREAM_PIPELINE_LITE_TRANSITIONS_KLING_REF_FILE = (
    PROMPTS_DIR / "dream_pipeline_lite_transitions_kling_v3_reference.md"
)
# Playground · Режиссёр: текст, который дописывается в user вместе с данными (не system markdown)
DREAM_DIRECTOR_REFERENCES_USER_CONTRACT_FILE = CONTRACTS_DIR / "dream_director_references_user.md"
DREAM_DIRECTOR_KEYFRAMES_USER_CONTRACT_FILE = CONTRACTS_DIR / "dream_director_keyframes_user.md"

_logged_system_prompt_path = False
_logged_global_policy_path = False
_logged_missing_global_policy = False
_logged_chat_video_tools_addon = False


class SystemPromptError(FileNotFoundError):
    """Файл промпта не найден или не читается."""


def get_system_prompt_path() -> Path:
    """Абсолютный путь к `prompts/system_prompt.md` в каталоге проекта."""
    return SYSTEM_PROMPT_FILE


def get_global_model_policy_path() -> Path:
    """Абсолютный путь к `prompts/global_model_policy.md`."""
    return GLOBAL_MODEL_POLICY_FILE


def get_dream_beat_planner_path() -> Path:
    """`prompts/dream_beat_planner.md` — system для Beat Planner (0A)."""
    return DREAM_BEAT_PLANNER_FILE


def get_dream_scene_motion_decompose_path() -> Path:
    """`prompts/dream_scene_motion_decompose.md` — сцены + motion для production `decompose_dream_scenes`."""
    return DREAM_SCENE_MOTION_DECOMPOSE_FILE


def get_dream_decomposition_path() -> Path:
    """`prompts/dream_decomposition.md` — system для Сценариста (0B), beats → scenes."""
    return DREAM_DECOMPOSITION_FILE


def get_dream_image_prompts_path() -> Path:
    """Абсолютный путь к `prompts/dream_image_prompts.md` (шаг 2 pipeline — image prompts)."""
    return DREAM_IMAGE_PROMPTS_FILE


def get_dream_intent_routing_path() -> Path:
    """Абсолютный путь к `prompts/dream_intent_routing.md` (маршрутизация dream vs chat)."""
    return DREAM_INTENT_ROUTING_FILE


def load_global_model_policy() -> str:
    """
    Дополнительный системный слой для **каждого** запроса к модели (политика, модерация).

    Подмешивается **к** уже заданному system (чат, pipeline и т.д.), не заменяет его.
    Читается при каждом вызове без кеша — правки в файле действуют со следующего запроса.

    Если файла нет или он пустой после trim — возвращается пустая строка (слой не добавляется).
    """
    global _logged_global_policy_path, _logged_missing_global_policy
    path = GLOBAL_MODEL_POLICY_FILE
    if not path.is_file():
        if not _logged_missing_global_policy:
            logger.warning(
                "Глобальная политика модели не найдена (%s) — дополнительный system не добавляется",
                path,
            )
            _logged_missing_global_policy = True
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.error("Не удалось прочитать global_model_policy: %s", e)
        return ""
    if text and not _logged_global_policy_path:
        logger.info(
            "Глобальная политика модели (доп. system) из %s",
            path.resolve(),
        )
        _logged_global_policy_path = True
    return text


def merge_with_global_model_policy(task_system: str) -> str:
    """
    Объединяет глобальный слой и системный промпт задачи в один блок для одного message role=system.

    Глобальный слой идёт первым (политика/цензура), затем разделитель и специфика задачи.
    """
    extra = load_global_model_policy()
    task = task_system or ""
    if not extra:
        return task
    if not task.strip():
        return extra
    return f"{extra}\n\n---\n\n{task}"


def load_chat_video_scenario_tools_addon() -> str:
    """
    Опциональный блок для чат-агента из ``chat_video_scenario_tools.md``.
    Если файла нет или после strip пусто — возвращает пустую строку.
    """
    global _logged_chat_video_tools_addon
    path = CHAT_VIDEO_SCENARIO_TOOLS_FILE
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning("Не удалось прочитать chat_video_scenario_tools: %s", e)
        return ""
    if text and not _logged_chat_video_tools_addon:
        logger.info("Чат-агент: доп. инструкции по видео из %s", path.resolve())
        _logged_chat_video_tools_addon = True
    return text


def load_system_prompt() -> str:
    """
    Читает системный промпт чат-агента из ``SYSTEM_PROMPT_FILE`` (``prompts/system_prompt.md``).

    Вызывается при каждом входящем текстовом сообщении в чат (без кеша в памяти):
    правки в файле применяются со **следующего** сообщения пользователя.
    Перезапуск сервера не требуется.
    """
    global _logged_system_prompt_path
    path = SYSTEM_PROMPT_FILE
    if not path.is_file():
        msg = f"Системный промпт не найден: {path}"
        logger.error(msg)
        raise SystemPromptError(msg)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.error("Не удалось прочитать system prompt: %s", e)
        raise SystemPromptError(str(e)) from e
    if not text:
        logger.error("Файл system_prompt.md пуст: %s", path)
        raise SystemPromptError("system_prompt.md пуст")
    if not _logged_system_prompt_path:
        logger.info(
            "Чат-агент: системный промпт из %s",
            path.resolve(),
        )
        _logged_system_prompt_path = True
    addon = load_chat_video_scenario_tools_addon()
    if addon:
        text = f"{text}\n\n---\n\n## Сценарий: изображения, видео и склейка\n\n{addon}"
    return text


def system_prompt_preview(max_len: int = 300) -> str:
    """Короткий превью для UI/логов (не полный текст)."""
    try:
        full = load_system_prompt()
    except SystemPromptError:
        return ""
    if len(full) <= max_len:
        return full
    return full[:max_len] + "…"


def read_system_prompt_raw() -> str:
    """Сырой текст `system_prompt.md` (для редактора; без strip — сохраняет форматирование)."""
    path = SYSTEM_PROMPT_FILE
    if not path.is_file():
        raise SystemPromptError(f"Системный промпт не найден: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise SystemPromptError(str(e)) from e


def write_system_prompt_raw(text: str) -> None:
    """Записывает `system_prompt.md` и сбрасывает флаг логирования первого чтения."""
    global _logged_system_prompt_path
    if not (text or "").strip():
        raise SystemPromptError("system_prompt.md не может быть пустым")
    path = SYSTEM_PROMPT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    _logged_system_prompt_path = False


def read_global_model_policy_raw() -> str:
    """Сырой текст `global_model_policy.md` (файл может отсутствовать — тогда пустая строка)."""
    path = GLOBAL_MODEL_POLICY_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать global_model_policy (raw): %s", e)
        return ""


def write_global_model_policy_raw(text: str) -> None:
    """Записывает `global_model_policy.md` (допустима пустая строка — слой не добавляется)."""
    global _logged_global_policy_path, _logged_missing_global_policy
    path = GLOBAL_MODEL_POLICY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")
    _logged_global_policy_path = False
    _logged_missing_global_policy = False


def read_dream_beat_planner_raw() -> str:
    path = DREAM_BEAT_PLANNER_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_beat_planner (raw): %s", e)
        return ""


def write_dream_beat_planner_raw(text: str) -> None:
    path = DREAM_BEAT_PLANNER_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_scene_motion_decompose_raw() -> str:
    path = DREAM_SCENE_MOTION_DECOMPOSE_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_scene_motion_decompose (raw): %s", e)
        return ""


def write_dream_scene_motion_decompose_raw(text: str) -> None:
    path = DREAM_SCENE_MOTION_DECOMPOSE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_decomposition_raw() -> str:
    """Сырой текст `dream_decomposition.md` (Сценарист 0B)."""
    path = DREAM_DECOMPOSITION_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_decomposition (raw): %s", e)
        return ""


def write_dream_decomposition_raw(text: str) -> None:
    """Записывает `dream_decomposition.md` (Сценарист 0B)."""
    path = DREAM_DECOMPOSITION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_image_prompts_raw() -> str:
    """Сырой текст `dream_image_prompts.md`; пустой — используется встроенный fallback в dream_scene_planner."""
    path = DREAM_IMAGE_PROMPTS_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_image_prompts (raw): %s", e)
        return ""


def write_dream_image_prompts_raw(text: str) -> None:
    path = DREAM_IMAGE_PROMPTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_intent_routing_raw() -> str:
    """Сырой текст `dream_intent_routing.md`; пустой — встроенный fallback в dream_orchestrator."""
    path = DREAM_INTENT_ROUTING_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_intent_routing (raw): %s", e)
        return ""


def write_dream_intent_routing_raw(text: str) -> None:
    path = DREAM_INTENT_ROUTING_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_director_references_raw() -> str:
    path = DREAM_DIRECTOR_REFERENCES_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_director_references: %s", e)
        return ""


def write_dream_director_references_raw(text: str) -> None:
    path = DREAM_DIRECTOR_REFERENCES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_director_keyframes_raw() -> str:
    path = DREAM_DIRECTOR_KEYFRAMES_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_director_keyframes: %s", e)
        return ""


def write_dream_director_keyframes_raw(text: str) -> None:
    path = DREAM_DIRECTOR_KEYFRAMES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_director_references_user_contract_raw() -> str:
    """Текст user-контракта 1A (`contracts/dream_director_references_user.md`). Пустой — fallback в коде."""
    path = DREAM_DIRECTOR_REFERENCES_USER_CONTRACT_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_director_references_user contract: %s", e)
        return ""


def write_dream_director_references_user_contract_raw(text: str) -> None:
    path = DREAM_DIRECTOR_REFERENCES_USER_CONTRACT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_director_keyframes_user_contract_raw() -> str:
    """Текст user-контракта 1B (`contracts/dream_director_keyframes_user.md`). Пустой — fallback в коде."""
    path = DREAM_DIRECTOR_KEYFRAMES_USER_CONTRACT_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_director_keyframes_user contract: %s", e)
        return ""


def write_dream_director_keyframes_user_contract_raw(text: str) -> None:
    path = DREAM_DIRECTOR_KEYFRAMES_USER_CONTRACT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_pipeline_lite_environments_raw() -> str:
    path = DREAM_PIPELINE_LITE_ENVIRONMENTS_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_pipeline_lite_environments: %s", e)
        return ""


def read_dream_pipeline_lite_environments_simple_raw() -> str:
    path = DREAM_PIPELINE_LITE_ENVIRONMENTS_SIMPLE_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_pipeline_lite_environments_simple: %s", e)
        return ""


def read_dream_pipeline_lite_frames_raw() -> str:
    path = DREAM_PIPELINE_LITE_FRAMES_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_pipeline_lite_frames: %s", e)
        return ""


def write_dream_pipeline_lite_environments_raw(text: str) -> None:
    path = DREAM_PIPELINE_LITE_ENVIRONMENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def write_dream_pipeline_lite_environments_simple_raw(text: str) -> None:
    path = DREAM_PIPELINE_LITE_ENVIRONMENTS_SIMPLE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def write_dream_pipeline_lite_frames_raw(text: str) -> None:
    path = DREAM_PIPELINE_LITE_FRAMES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_pipeline_lite_frames_prev_link_raw() -> str:
    path = DREAM_PIPELINE_LITE_FRAMES_PREV_LINK_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_pipeline_lite_frames_prev_link: %s", e)
        return ""


def write_dream_pipeline_lite_frames_prev_link_raw(text: str) -> None:
    path = DREAM_PIPELINE_LITE_FRAMES_PREV_LINK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_pipeline_lite_transitions_raw() -> str:
    path = DREAM_PIPELINE_LITE_TRANSITIONS_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_pipeline_lite_transitions: %s", e)
        return ""


def write_dream_pipeline_lite_transitions_raw(text: str) -> None:
    path = DREAM_PIPELINE_LITE_TRANSITIONS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_pipeline_lite_transitions_seedance_raw() -> str:
    path = DREAM_PIPELINE_LITE_TRANSITIONS_SEEDANCE_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_pipeline_lite_transitions_seedance: %s", e)
        return ""


def write_dream_pipeline_lite_transitions_seedance_raw(text: str) -> None:
    path = DREAM_PIPELINE_LITE_TRANSITIONS_SEEDANCE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_pipeline_lite_transitions_wan26_raw() -> str:
    path = DREAM_PIPELINE_LITE_TRANSITIONS_WAN26_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_pipeline_lite_transitions_wan26: %s", e)
        return ""


def write_dream_pipeline_lite_transitions_wan26_raw(text: str) -> None:
    path = DREAM_PIPELINE_LITE_TRANSITIONS_WAN26_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")


def read_dream_pipeline_lite_transitions_kling_ref_raw() -> str:
    path = DREAM_PIPELINE_LITE_TRANSITIONS_KLING_REF_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Не удалось прочитать dream_pipeline_lite_transitions_kling_ref: %s", e)
        return ""


def write_dream_pipeline_lite_transitions_kling_ref_raw(text: str) -> None:
    path = DREAM_PIPELINE_LITE_TRANSITIONS_KLING_REF_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8", newline="\n")
