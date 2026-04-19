"""Загрузка системных промптов из markdown-файлов (без кеша — правки подхватываются сразу)."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Корень проекта: services/llm → services → корень (не зависит от текущей рабочей директории)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = _PROJECT_ROOT / "prompts"
# Единственный файл системного промпта для чат-агента (ChatOrchestrator → OpenAI)
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system_prompt.md"
# Дополнительный слой system для всех вызовов OpenAI (чат, dream JSON и т.д.)
GLOBAL_MODEL_POLICY_FILE = PROMPTS_DIR / "global_model_policy.md"

_logged_system_prompt_path = False
_logged_global_policy_path = False
_logged_missing_global_policy = False


class SystemPromptError(FileNotFoundError):
    """Файл промпта не найден или не читается."""


def get_system_prompt_path() -> Path:
    """Абсолютный путь к `prompts/system_prompt.md` в каталоге проекта."""
    return SYSTEM_PROMPT_FILE


def get_global_model_policy_path() -> Path:
    """Абсолютный путь к `prompts/global_model_policy.md`."""
    return GLOBAL_MODEL_POLICY_FILE


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
