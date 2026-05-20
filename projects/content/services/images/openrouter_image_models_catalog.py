"""
Курируемый список моделей OpenRouter для генерации изображений (вход: text + image в messages).

Авто-fallback Dream Lite использует только модели с **выходом** image и text (modalities в API);
остальные (Flux и др.) — для ручного выбора. Сверка с API: список models с output image+text.

Цены — ориентиры по страницам OpenRouter / каталогу; уточняйте на https://openrouter.ai/models
"""
from __future__ import annotations

import re
from typing import Any

# id — как в API OpenRouter; label — коротко для UI; cost_hint — ориентир для выбора
OPENROUTER_IMAGE_MODELS_CATALOG: list[dict[str, Any]] = [
    {
        "id": "google/gemini-2.5-flash-image",
        "label": "Gemini 2.5 Flash Image",
        "description": "Быстрая модель Google для картинок; хорошо подходит для итераций и референсов в одном запросе.",
        "cost_hint": "Цена: низкий–средний (по токенам; см. карточку модели)",
        "supports_reference_images": True,
    },
    {
        "id": "google/gemini-3.1-flash-image-preview",
        "label": "Gemini 3.1 Flash Image (preview)",
        "description": "Новее flash; расширенные соотношения сторон и размер 0.5K–4K в image_config.",
        "cost_hint": "Цена: низкий–средний",
        "supports_reference_images": True,
    },
    {
        "id": "google/gemini-3-pro-image-preview",
        "label": "Gemini 3 Pro Image (preview)",
        "description": "Как у других Gemini image на OpenRouter: вход text+image (референсы), выход image+text — тот же режим modalities, что и у основной цепочки Dream Lite.",
        "cost_hint": "Цена: см. карточку модели",
        "supports_reference_images": True,
    },
    {
        "id": "openai/gpt-5-image-mini",
        "label": "GPT-5 Image Mini",
        "description": "OpenRouter: выход image+text; подходит как запасной маршрут с референсами в messages (как Gemini image).",
        "cost_hint": "Цена: см. OpenRouter",
        "supports_reference_images": True,
    },
    {
        "id": "openai/gpt-5-image",
        "label": "GPT-5 Image",
        "description": "OpenRouter: image+text output; альтернатива при недоступности Gemini.",
        "cost_hint": "Цена: см. OpenRouter",
        "supports_reference_images": True,
    },
    {
        "id": "openai/gpt-5.4-image-2",
        "label": "GPT-5.4 Image 2",
        "description": "OpenRouter: выход image+text; запасной вариант в автоцепочке Dream Lite.",
        "cost_hint": "Цена: см. OpenRouter",
        "supports_reference_images": True,
    },
    {
        "id": "bytedance-seed/seedream-4.5",
        "label": "Seedream 4.5 (ByteDance)",
        "description": "Генерация и редактирование; на OpenRouter выход часто **только image** (как Flux) — не в авто-fallback Dream Lite. Референсы + текст в messages при ручном выборе возможны.",
        "cost_hint": "Цена: ~$0.04 за изображение (OpenRouter)",
        "supports_reference_images": True,
    },
    {
        "id": "black-forest-labs/flux.2-pro",
        "label": "Flux 2 Pro",
        "description": "BFL: на OpenRouter **выход только image** (без текстового канала) — modalities в API отличаются от Gemini; для референсов+текста на входе подходит, но автопайплайн Dream Lite в fallback цепочке использует только модели image+text output.",
        "cost_hint": "Цена: средний–высокий (провайдер BFL)",
        "supports_reference_images": True,
    },
    {
        "id": "black-forest-labs/flux.2-flex",
        "label": "Flux 2 Flex",
        "description": "Как Flux 2 Pro: **выход image-only** на OpenRouter; оставлен в каталоге для ручного выбора.",
        "cost_hint": "Цена: средний",
        "supports_reference_images": True,
    },
    {
        "id": "qwen/qwen-image",
        "label": "Qwen Image",
        "description": "Может быть недоступна на OpenRouter (HTTP 400: not a valid model ID); не используется в авто-fallback.",
        "cost_hint": "Цена: обычно ниже премиум-моделей",
        "supports_reference_images": False,
    },
]

# Авто-fallback после primary и OPENROUTER_IMAGE_MODEL_FALLBACK: только модели, у которых на
# OpenRouter в architecture.output_modalities одновременно image и text (как у Gemini image),
# чтобы везде в tool оставались modalities ["image", "text"] и не ломался единый контракт.
# Проверка актуального списка: GET /api/v1/models и фильтр по output_modalities.
# Flux/Seedream — выход часто только image → не включаем в автоцепочку (доступны вручную в UI).
OPENROUTER_IMAGE_FALLBACK_CHAIN_EXTRA: tuple[str, ...] = (
    "google/gemini-3.1-flash-image-preview",
    "google/gemini-3-pro-image-preview",
    "google/gemini-2.5-flash-image",
    "openai/gpt-5-image-mini",
    "openai/gpt-5-image",
    "openai/gpt-5.4-image-2",
)

# Явный список (дублирует проверку API; при сомнениях сверяйте с OpenRouter).
_OPENROUTER_IMAGE_AND_TEXT_OUTPUT_IDS: frozenset[str] = frozenset(
    {
        "google/gemini-2.5-flash-image",
        "google/gemini-3.1-flash-image-preview",
        "google/gemini-3-pro-image-preview",
        "openai/gpt-5-image",
        "openai/gpt-5-image-mini",
        "openai/gpt-5.4-image-2",
    }
)


def openrouter_model_supports_image_and_text_output(resolved_model_id: str) -> bool:
    """
    True, если для model id безопасно отправлять modalities ["image", "text"] (выход и картинка, и текст),
    как в доке OpenRouter для Gemini / GPT image. Иначе — только ["image"] (Flux и др.).
    `resolved_model_id` — уже slug вида vendor/name.
    """
    mid = (resolved_model_id or "").strip().lower()
    if not mid:
        return False
    if mid in _OPENROUTER_IMAGE_AND_TEXT_OUTPUT_IDS:
        return True
    # Новые id того же семейства без немедленного обновления frozenset
    if mid.startswith("google/") and "gemini" in mid and "image" in mid:
        return True
    if mid.startswith("openai/") and "image" in mid:
        return True
    return False


def openrouter_image_models_try_chain(
    *,
    primary_resolved: str,
    settings_fallback_resolved: str,
) -> list[str]:
    """
    Уникальная последовательность model id для tool_generate_image_openrouter:
    сначала основная и fallback из настроек, затем OPENROUTER_IMAGE_FALLBACK_CHAIN_EXTRA.
    """
    out: list[str] = []
    for m in (primary_resolved, settings_fallback_resolved):
        mid = (m or "").strip()
        if mid and "/" in mid and mid not in out:
            out.append(mid)
    for m in OPENROUTER_IMAGE_FALLBACK_CHAIN_EXTRA:
        if m not in out:
            out.append(m)
    return out


def catalog_models_for_template(
    *,
    settings_default_id: str,
    settings_fallback_id: str,
) -> list[dict[str, Any]]:
    """Порядок: дефолт из настроек первым, затем остальные без дубликатов."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    extra_ids = [settings_default_id, settings_fallback_id]
    by_id = {str(m["id"]): m for m in OPENROUTER_IMAGE_MODELS_CATALOG}

    for raw in extra_ids:
        mid = (raw or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        if mid in by_id:
            row = dict(by_id[mid])
        else:
            row = {
                "id": mid,
                "label": mid.split("/")[-1] if "/" in mid else mid,
                "description": "Модель из настроек окружения; описание см. на openrouter.ai.",
                "cost_hint": "Цена: см. каталог OpenRouter",
                "supports_reference_images": True,
            }
        if not str(row.get("cost_hint") or "").strip():
            row["cost_hint"] = "Цена: см. каталог OpenRouter"
        row["is_settings_default"] = mid == (settings_default_id or "").strip()
        row["is_settings_fallback"] = mid == (settings_fallback_id or "").strip()
        out.append(row)

    for m in OPENROUTER_IMAGE_MODELS_CATALOG:
        mid = str(m["id"])
        if mid in seen:
            continue
        seen.add(mid)
        row = dict(m)
        if not str(row.get("cost_hint") or "").strip():
            row["cost_hint"] = "Цена: см. каталог OpenRouter"
        row["is_settings_default"] = mid == (settings_default_id or "").strip()
        row["is_settings_fallback"] = mid == (settings_fallback_id or "").strip()
        out.append(row)
    return out


def openrouter_model_supports_reference_images(resolved_model_id: str) -> bool:
    mid = (resolved_model_id or "").strip()
    if not mid:
        return False
    for row in OPENROUTER_IMAGE_MODELS_CATALOG:
        if str(row.get("id") or "").strip() == mid:
            return bool(row.get("supports_reference_images", True))
    # Для новых/кастомных моделей сохраняем controlled fallback-поведение.
    return True


def _normalize_openrouter_model_input(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    t = t.replace("—", "-").replace("–", "-").replace("−", "-")
    # если в value по ошибке попала подпись опции «Label — hint»
    if " — " in t:
        t = t.split(" — ", 1)[0].strip()
    return t


def resolve_openrouter_image_model_id(raw: str | None) -> str:
    """
    Приводит значение поля model к id вида vendor/name для OpenRouter.

    HTTP 400 вида «… is not valid model» часто из-за человекочитаемой подписи
    («Qwen Image», «Gemini 2.5 Flash Image») вместо slug, или опечатки в .env.
    Произвольную строку без «/» в API не отдаём.
    """
    s = _normalize_openrouter_model_input(str(raw or ""))
    if not s:
        return ""
    if "/" in s:
        return s.split()[0].strip()
    low = re.sub(r"\s+", " ", s.lower().strip())
    typo_map = {
        "qwen image": "qwen/qwen-image",
        "gaven image": "qwen/qwen-image",
        "given image": "qwen/qwen-image",
        "gemini 2.5 flash image": "google/gemini-2.5-flash-image",
        "gemini 3.1 flash image (preview)": "google/gemini-3.1-flash-image-preview",
        "gemini 3.1 flash image": "google/gemini-3.1-flash-image-preview",
        "gemini 3 pro image": "google/gemini-3-pro-image-preview",
        "gemini 3 pro image (preview)": "google/gemini-3-pro-image-preview",
        "seedream 4.5 (bytedance)": "bytedance-seed/seedream-4.5",
        "seedream 4.5": "bytedance-seed/seedream-4.5",
        "seadream": "bytedance-seed/seedream-4.5",
        "sea dream": "bytedance-seed/seedream-4.5",
        "flux 2 pro": "black-forest-labs/flux.2-pro",
        "flux 2 flex": "black-forest-labs/flux.2-flex",
    }
    if low in typo_map:
        return typo_map[low]
    for m in OPENROUTER_IMAGE_MODELS_CATALOG:
        if low == str(m.get("label") or "").lower():
            return str(m["id"])
        tail = str(m.get("id") or "").split("/")[-1].lower()
        if low == tail:
            return str(m["id"])
    if "qwen" in low and "image" in low:
        return "qwen/qwen-image"
    if "seedream" in low or "seadream" in low or "sea dream" in low:
        return "bytedance-seed/seedream-4.5"
    return ""
