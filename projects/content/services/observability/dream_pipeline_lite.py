"""
Dream Pipeline Lite: шаг 1 (персонажи + окружения) → шаг 2 (кадры) → визуал → план монтажа (сцены, переходы).

Парсинг — markdown ## / ### (см. prompts/dream_pipeline_lite_*.md); финальный шаг — JSON из чата.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

# Строки длиннее — выносим в файлы под ui/dev/static, иначе Mongo 16MB и data URI в документе.
_LITE_MONGO_INLINE_MAX = 9000

# OpenRouter `image_config`: без явных полей провайдер часто отдаёт крупный дефолт (вплоть до 4K) —
# тяжело для превью и для открытия data:-URL в новой вкладке. Для телефона: вертикаль + ~1K.
LITE_OPENROUTER_IMAGE_ASPECT_RATIO = "9:16"
LITE_OPENROUTER_IMAGE_SIZE = "1K"

from services.llm.system_prompt_loader import (
    read_dream_pipeline_lite_environments_raw,
    read_dream_pipeline_lite_environments_simple_raw,
    read_dream_pipeline_lite_frames_raw,
    read_dream_pipeline_lite_frames_prev_link_raw,
    read_dream_pipeline_lite_transitions_kling_ref_raw,
    read_dream_pipeline_lite_transitions_seedance_raw,
    read_dream_pipeline_lite_transitions_raw,
    read_dream_pipeline_lite_transitions_wan26_raw,
)
from services.tools.openrouter_image_tools import tool_generate_image_openrouter


def _lite_package_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _lite_dev_static_root() -> Path:
    return _lite_package_root() / "ui" / "dev" / "static"


def lite_fs_path_from_dev_static_url(dev_static_url: str) -> Path | None:
    """
    URL вида /dev/static/... → абсолютный путь под ui/dev/static (для отправки файла в Telegram и т.п.).
    """
    u = (dev_static_url or "").strip()
    prefix = "/dev/static/"
    if not u.startswith(prefix):
        return None
    rel = u[len(prefix) :].lstrip("/")
    if not rel or any(p == ".." for p in rel.split("/")):
        return None
    root = _lite_dev_static_root().resolve()
    p = (root / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def _lite_sanitize_run_stem(s: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9._-]+", "_", (s or "").strip())
    return (t[:64] if t else "run").strip("_") or "run"


def _lite_sanitize_basename(s: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9._-]+", "_", (s or "").strip())
    return (t[:80] if t else "x").strip("_") or "x"


def lite_run_asset_dir(user_id: int, lite_run_id: str) -> Path:
    """Файлы кадров: dream_lite_runs/{user_id}/{lite_run_id}/ — изоляция по пользователю."""
    uid = int(user_id)
    d = (
        _lite_dev_static_root()
        / "dream_lite_runs"
        / str(uid)
        / _lite_sanitize_run_stem(lite_run_id)
    )
    d.mkdir(parents=True, exist_ok=True)
    return d


# Playground / dev запускается от отдельного настраиваемого user_id
# (по умолчанию реальный Telegram user id владельца стенда) для parity с Telegram-веткой.
LITE_PLAYGROUND_USER_ID = int(get_settings().dream_lite_playground_user_id)
LITE_STEP2_RUNTIME_ENTRYPOINT = "lite_run_step2_frames_with_prev_link"


def lite_materialize_image_url_for_mongo(
    url: str,
    *,
    lite_run_id: str,
    basename: str,
    user_id: int = LITE_PLAYGROUND_USER_ID,
) -> str:
    """
    Укладывает data URI / слишком длинные URL в файл под /dev/static/dream_lite_runs/...
    В Mongo остаётся короткий путь; перед вызовом OpenRouter используйте lite_resolve_image_url_for_external_api.
    """
    u = (url or "").strip()
    if not u:
        return u
    if u.startswith("/dev/static/"):
        return u
    if not u.startswith("data:") and len(u) <= _LITE_MONGO_INLINE_MAX:
        return u

    run_dir = lite_run_asset_dir(user_id, lite_run_id)
    stem = _lite_sanitize_basename(basename)[:72] or "img"
    uniq = uuid.uuid4().hex[:10]
    raw: bytes
    ext = ".bin"

    if u.startswith("data:"):
        m = re.match(
            r"data:([^;]+);base64,(.+)",
            u,
            re.DOTALL | re.IGNORECASE,
        )
        if not m:
            logger.warning("dream_lite: неразборчивый data URI, усечение для Mongo")
            return u[:400] + f"…(omit len={len(u)})"
        mime = (m.group(1) or "").lower()
        try:
            raw = base64.b64decode(m.group(2).strip(), validate=False)
        except Exception:
            logger.exception("dream_lite: ошибка base64 в materialize")
            return u[:400] + "…"
        if "png" in mime:
            ext = ".png"
        elif "jpeg" in mime or "jpg" in mime:
            ext = ".jpg"
        elif "webp" in mime:
            ext = ".webp"
    elif u.startswith("http://") or u.startswith("https://"):
        try:
            req = urllib.request.Request(
                u,
                headers={"User-Agent": "Mozilla/5.0 DreamPipelineLite/1"},
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read()
                ct = (resp.headers.get("Content-Type") or "").lower()
            if "png" in ct:
                ext = ".png"
            elif "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "webp" in ct:
                ext = ".webp"
        except (urllib.error.URLError, OSError, ValueError) as e:
            logger.warning("dream_lite: не удалось скачать URL для materialize: %s", e)
            return u[: _LITE_MONGO_INLINE_MAX] + f"…(trunc,len={len(u)})"
    else:
        raw = u.encode("utf-8")

    fname = f"{stem}_{uniq}{ext}"
    path = run_dir / fname
    path.write_bytes(raw)
    try:
        rel = path.resolve().relative_to(_lite_dev_static_root().resolve())
    except ValueError:
        rel = Path("dream_lite_runs") / run_dir.name / fname
    return "/dev/static/" + rel.as_posix()


def lite_materialize_url_list_for_mongo(
    urls: list[str],
    *,
    lite_run_id: str,
    basename_prefix: str,
    user_id: int = LITE_PLAYGROUND_USER_ID,
) -> list[str]:
    pref = _lite_sanitize_basename(basename_prefix)
    return [
        lite_materialize_image_url_for_mongo(
            str(u or ""),
            lite_run_id=lite_run_id,
            basename=f"{pref}_{i}",
            user_id=user_id,
        )
        for i, u in enumerate(urls)
    ]


def lite_materialize_frame_results_inplace(
    frame_results: list[dict[str, Any]],
    *,
    user_id: int,
    lite_run_id: str,
) -> None:
    """
    Заменяет data URI / длинные URL в результатах кадров на /dev/static/... под каталог пользователя.
    Обновляет reference_image_urls_ui для слотов, где есть url.
    """
    for d in frame_results or []:
        if not isinstance(d, dict):
            continue
        ix = d.get("index")
        if ix is None:
            ix = 0
        ix = int(ix)
        urls = list(d.get("urls") or [])
        if urls:
            d["urls"] = lite_materialize_url_list_for_mongo(
                urls,
                lite_run_id=lite_run_id,
                basename_prefix=f"out_frame_{ix}",
                user_id=user_id,
            )
        refs = list(d.get("reference_image_urls") or [])
        if refs:
            d["reference_image_urls"] = lite_materialize_url_list_for_mongo(
                refs,
                lite_run_id=lite_run_id,
                basename_prefix=f"ref_frame_{ix}",
                user_id=user_id,
            )
        new_refs = list(d.get("reference_image_urls") or [])
        slots = d.get("ref_slots")
        if isinstance(slots, list) and new_refs:
            for s in slots:
                if not isinstance(s, dict):
                    continue
                o = s.get("order")
                if o is None:
                    continue
                j = int(o) - 1
                if 0 <= j < len(new_refs):
                    s["url"] = new_refs[j]
        if d.get("reference_image_urls"):
            d["reference_image_urls_ui"] = lite_ref_urls_for_ui(
                list(d["reference_image_urls"])
            )


def lite_resolve_image_url_for_external_api(url: str | None) -> str | None:
    """Локальный /dev/static/... → data URI для OpenRouter / провайдеров, ожидающих встраиваемое изображение."""
    u = (url or "").strip()
    if not u:
        return None
    if u.startswith("data:") or u.startswith("http://") or u.startswith("https://"):
        return u
    if not u.startswith("/dev/static/"):
        return u
    rel = u[len("/dev/static/") :].lstrip("/")
    base = _lite_dev_static_root().resolve()
    path = (base / rel).resolve()
    if not str(path).startswith(str(base)):
        logger.warning("dream_lite resolve: выход за пределы static: %s", path)
        return None
    if not path.is_file():
        return u
    try:
        raw = path.read_bytes()
    except OSError:
        return u
    suf = path.suffix.lower()
    mime = "image/png"
    if suf in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif suf == ".webp":
        mime = "image/webp"
    elif suf == ".bin":
        mime = "application/octet-stream"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def lite_environments_system_prompt(*, simple_mode: bool = False) -> str:
    if simple_mode:
        raw_simple = (read_dream_pipeline_lite_environments_simple_raw() or "").strip()
        if raw_simple:
            return raw_simple
        return (
            "Шаг 1 Dream Lite (simple mode): сгенерируй markdown-блоки ## Окружения и ## Персонажи. "
            "Окружения описывай как пустую сцену без любых живых существ: без людей, животных, птиц, "
            "насекомых, толп, силуэтов и персонажей вдали. Разрешены только пространство, свет, материалы, "
            "атмосфера и зона действия. Если в тексте сна есть живые существа, в окружениях их всё равно не добавляй. "
            "Персонажи — отдельные атомарные карточки людей. Без JSON, без «я»."
        )
    raw = (read_dream_pipeline_lite_environments_raw() or "").strip()
    if raw:
        return raw
    return (
        "Шаг 1 Dream Lite: ## Окружения и ## Персонажи. Окружения по умолчанию — человеческий масштаб, сцена для действия "
        "(уровень глаз, передний план, зона события); широкий/дальний план — только если масштаб явно в тексте сна. "
        "Персонажи — только люди, карточка атомарна (reference sheet без взаимодействий с другими); "
        "животные, толпы, предметы, абстракции — в окружении/кадре, не в персонажах. Без «я», без JSON."
    )


def lite_frames_system_prompt() -> str:
    raw = (read_dream_pipeline_lite_frames_raw() or "").strip()
    if raw:
        return raw
    return (
        "Раскадровка: много кадров, одно действие на кадр; base_reference, character_references (включая dreamer при участии), "
        "delta, frame_text. Поля use_previous_frame и is_keyframe **не** указывай — их задаёт отдельный шаг модели после раскадровки. Без «я», без JSON."
    )


def lite_environments_user_message(dream_text: str) -> str:
    t = (dream_text or "").strip()
    return f"Текст сна:\n\n{t if t else '(пусто)'}\n"


def lite_frames_user_message(dream_text: str, step1_text: str) -> str:
    d = (dream_text or "").strip()
    s1 = (step1_text or "").strip()
    return (
        "Текст сна:\n\n"
        f"{d if d else '(пусто)'}\n\n"
        "---\n\n"
        "Шаг 1 (окружения и персонажи):\n\n"
        f"{s1 if s1 else '(сначала выполните шаг 1)'}\n"
    )


def lite_frames_prev_link_system_prompt() -> str:
    raw = (read_dream_pipeline_lite_frames_prev_link_raw() or "").strip()
    if raw:
        return raw
    return (
        "Ты классификатор: по раскадровке (markdown) и контексту сна решаешь для каждого кадра два флага: "
        "(1) нужен ли в image API референс **предыдущего сгенерированного кадра** (continuity), "
        "(2) является ли кадр **ключевым** для генерации картинки в light mode. "
        "Ответь **одним JSON-объектом** без markdown. "
        "Формат: {\"use_previous_frame_by_index\": [..], \"keyframe_by_index\": [..], \"keyframe_reason_by_index\": [..]}. "
        "Все массивы длины **ровно N** (порядок как ### Кадр 1..N). "
        "Первый элемент use_previous_frame_by_index всегда false. "
        "Ключевых кадров должно быть заметно меньше общего числа; выбирай только сюжетно важные точки."
    )


def lite_frames_prev_link_user_message(
    dream_text: str, step1_text: str, frames_markdown: str
) -> str:
    d = (dream_text or "").strip()
    s1 = (step1_text or "").strip()
    fm = (frames_markdown or "").strip()
    return (
        "Текст сна:\n\n"
        f"{d if d else '(пусто)'}\n\n"
        "---\n\n"
        "Шаг 1 (окружения и персонажи):\n\n"
        f"{s1 if s1 else '(нет)'}\n\n"
        "---\n\n"
        "Раскадровка (шаг 2a, markdown — только для классификации prev):\n\n"
        f"{fm if fm else '(пусто)'}\n"
    )


def _lite_extract_json_value(text: str) -> str | None:
    t = (text or "").strip()
    if "```" in t:
        parts = t.split("```")
        for i, p in enumerate(parts):
            if i % 2 != 1:
                continue
            block = p.lstrip()
            if block.lower().startswith("json"):
                block = block[4:].lstrip()
            cand = block.strip()
            if cand.startswith("{") or cand.startswith("["):
                return cand
    for opener, closer in (("{", "}"), ("[", "]")):
        start = t.find(opener)
        if start < 0:
            continue
        depth = 0
        for j in range(start, len(t)):
            if t[j] == opener:
                depth += 1
            elif t[j] == closer:
                depth -= 1
                if depth == 0:
                    return t[start : j + 1]
    return None


def parse_lite_frames_prev_link_response(
    raw: str,
    *,
    n_frames: int,
) -> tuple[list[bool], list[bool], list[str]]:
    """Флаги по кадрам: (use_previous_by_index, keyframe_by_index, keyframe_reason_by_index)."""
    if n_frames <= 0:
        return []
    blob = _lite_extract_json_value(raw)
    if not blob:
        raise ValueError("В ответе классификатора prev не найден JSON")
    try:
        obj: Any = json.loads(blob)
    except json.JSONDecodeError as e:
        raise ValueError(f"Некорректный JSON классификатора prev: {e}") from e
    arr_prev: list[Any] | None = None
    arr_key: list[Any] | None = None
    arr_reason: list[Any] | None = None
    if isinstance(obj, list) and len(obj) == n_frames:
        arr_prev = list(obj)
        arr_key = [True] * n_frames
        arr_reason = ["legacy_prev_only_contract"] * n_frames
    elif isinstance(obj, dict):
        v = obj.get("use_previous_frame_by_index")
        if isinstance(v, list) and len(v) == n_frames:
            arr_prev = list(v)
        vk = obj.get("keyframe_by_index")
        if isinstance(vk, list) and len(vk) == n_frames:
            arr_key = list(vk)
        vr = obj.get("keyframe_reason_by_index")
        if isinstance(vr, list) and len(vr) == n_frames:
            arr_reason = list(vr)
        if isinstance(obj.get("frames"), list):
            fr = obj["frames"]
            by_i: dict[int, bool] = {}
            by_k: dict[int, bool] = {}
            by_r: dict[int, str] = {}
            for it in fr:
                if not isinstance(it, dict):
                    continue
                try:
                    ix = int(it.get("index"))
                except (TypeError, ValueError):
                    continue
                u = it.get("use_previous_frame", it.get("links_to_previous"))
                if isinstance(u, bool):
                    by_i[ix] = u
                elif isinstance(u, str):
                    by_i[ix] = _parse_bool_loose(u) is True
                kf = it.get("is_keyframe", it.get("keyframe"))
                if isinstance(kf, bool):
                    by_k[ix] = kf
                elif isinstance(kf, str):
                    parsed_k = _parse_bool_loose(kf)
                    if parsed_k is not None:
                        by_k[ix] = parsed_k
                rs = str(it.get("keyframe_reason") or it.get("reason") or "").strip()
                if rs:
                    by_r[ix] = rs
            if all(i in by_i for i in range(n_frames)) and arr_prev is None:
                arr_prev = [bool(by_i.get(i, False)) for i in range(n_frames)]
            if by_k and arr_key is None:
                arr_key = [bool(by_k.get(i, False)) for i in range(n_frames)]
            if by_r and arr_reason is None:
                arr_reason = [str(by_r.get(i, "")) for i in range(n_frames)]
    if arr_prev is None:
        raise ValueError(
            f"Ожидался массив из {n_frames} решений (use_previous_frame_by_index или frames[])"
        )
    out_prev: list[bool] = []
    for i, x in enumerate(arr_prev):
        if i >= n_frames:
            break
        if i == 0:
            out_prev.append(False)
            continue
        if isinstance(x, bool):
            out_prev.append(x)
        elif isinstance(x, (int, float)):
            out_prev.append(bool(x))
        elif isinstance(x, str) and x.strip():
            out_prev.append(_parse_bool_loose(x) is True)
        else:
            out_prev.append(False)
    while len(out_prev) < n_frames:
        out_prev.append(False)
    if len(out_prev) != n_frames:
        out_prev = out_prev[:n_frames]
    out_prev[0] = False

    out_key: list[bool] = []
    src_key = list(arr_key) if isinstance(arr_key, list) and len(arr_key) == n_frames else [True] * n_frames
    for i, x in enumerate(src_key):
        if i >= n_frames:
            break
        if isinstance(x, bool):
            out_key.append(x)
        elif isinstance(x, (int, float)):
            out_key.append(bool(x))
        elif isinstance(x, str) and x.strip():
            out_key.append(_parse_bool_loose(x) is True)
        else:
            out_key.append(False)
    while len(out_key) < n_frames:
        out_key.append(True)
    if not any(out_key):
        out_key[0] = True
    if n_frames >= 3 and sum(1 for x in out_key if x) < 2:
        out_key[-1] = True

    out_reason: list[str] = []
    src_reason = list(arr_reason) if isinstance(arr_reason, list) and len(arr_reason) == n_frames else [""] * n_frames
    for i in range(n_frames):
        reason = str(src_reason[i] or "").strip() if i < len(src_reason) else ""
        if out_key[i] and not reason:
            reason = "выбран как ключевой сюжетный кадр"
        out_reason.append(reason)
    return out_prev, out_key, out_reason


def lite_reapply_prev_chain_on_cards(cards: list[dict[str, Any]]) -> None:
    """Пересчитать use_previous_frame_resolved и UI-поля после смены use_previous_frame."""
    prior: list[dict[str, Any]] = []
    for i, d in enumerate(cards):
        if not isinstance(d, dict):
            continue
        up_eff, forced = lite_resolve_use_previous_frame(
            d,
            i,
            prior_frame_entries=prior,
            simple_mode=bool(d.get("simple_mode")),
        )
        d["use_previous_frame_resolved"] = up_eff
        d["forced_prev_chain_break"] = forced
        prior.append({"use_previous_frame_resolved": up_eff})
        _append_lite_frame_ui_fields(i, d)


def lite_apply_prev_link_classifier_raw(
    cards: list[dict[str, Any]], classifier_raw: str
) -> None:
    if not cards:
        return
    flags_prev, flags_key, flags_reason = parse_lite_frames_prev_link_response(
        classifier_raw, n_frames=len(cards)
    )
    for i, c in enumerate(cards):
        if not isinstance(c, dict):
            continue
        want = bool(flags_prev[i]) if i < len(flags_prev) else False
        if i == 0:
            want = False
        c["use_previous_frame"] = want
        c["is_keyframe"] = bool(flags_key[i]) if i < len(flags_key) else True
        c["keyframe_reason"] = str(flags_reason[i] or "").strip() if i < len(flags_reason) else ""
    lite_reapply_prev_chain_on_cards(cards)


def lite_frame_cards_for_visual_from_text(
    frames_text: str,
    *,
    step1_char_titles: list[str] | None = None,
    frames_prev_link_raw: str | None = None,
) -> list[dict[str, Any]]:
    """
    Шаг 3: снова парсит markdown 2a и enrich; если в форму передан сырой ответ 2b —
    применяет те же флаги prev, что и на шаге 2 (иначе в markdown prev нет — всё «без prev»).
    """
    cards = enrich_lite_frame_cards(
        split_lite_frame_cards((frames_text or "").strip()),
        step1_char_titles=step1_char_titles,
    )
    blob = (frames_prev_link_raw or "").strip()
    if not blob:
        return cards
    try:
        lite_apply_prev_link_classifier_raw(cards, blob)
    except ValueError as exc:
        logger.warning(
            "dream_lite шаг 3: prev_link JSON не применён (%s); кадры без цепочки prev",
            exc,
        )
    return cards


async def lite_run_step2_frames_with_prev_link(
    openai: Any,
    *,
    dream_text: str,
    step1_markdown: str,
    step2_system_prompt: str | None = None,
    prev_link_system_prompt: str | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Шаг 2: (a) раскадровка, (b) классификатор prev → обогащённые карточки.
    Возвращает (raw раскадровки, raw ответа классификатора, cards).
    """
    dt = (dream_text or "").strip()
    s1 = (step1_markdown or "").strip()
    step2_raw = await lite_chat_text(
        openai,
        system=(step2_system_prompt or "").strip() or lite_frames_system_prompt(),
        user=lite_frames_user_message(dt, s1),
    )
    _, char_cards = split_lite_step1_world(s1)
    char_titles = [
        str(c.get("title") or "").strip() for c in char_cards if c.get("title")
    ]
    cards = enrich_lite_frame_cards(
        split_lite_frame_cards(step2_raw),
        step1_char_titles=char_titles,
    )
    prev_raw = await lite_chat_text(
        openai,
        system=(prev_link_system_prompt or "").strip() or lite_frames_prev_link_system_prompt(),
        user=lite_frames_prev_link_user_message(dt, s1, step2_raw),
    )
    lite_apply_prev_link_classifier_raw(cards, prev_raw)
    return step2_raw, prev_raw, cards


def lite_transitions_system_prompt() -> str:
    raw = (read_dream_pipeline_lite_transitions_raw() or "").strip()
    if raw:
        return raw
    return (
        "План монтажа: выбор опорных кадров из полного набора; между кадрами animate_transition или hard_cut. "
        "Верни один JSON с ключами scenes, transitions, keyframes, frame_selection. "
        "frame_selection: массив объектов {frame_index, selected, reason}; для selected=true reason обязателен. "
        "Работай только по текстовому JSON-контракту (id/prompt/метаданные), без inline image bytes/base64. "
        "Без «я», без markdown."
    )


def lite_transitions_seedance_system_prompt() -> str:
    raw = (read_dream_pipeline_lite_transitions_seedance_raw() or "").strip()
    if raw:
        return raw
    return (
        "План монтажа для Seedance: один animate-сегмент на каждый промежуток между соседними keyframes. "
        "Для animate_transition добавляй segment_mode=pairwise|single_anchor, motion_prompt, duration_sec, segment_story; "
        "при audio_required=true добавляй voiceover_text. "
        "motion_prompt пиши только как финальный текст для i2v: 1-3 коротких предложения, только текущий keyframe-gap, "
        "без служебных меток и без пересказа всего сна. "
        "В motion_prompt разрешён короткий функциональный диалог действия (например: просьба -> обсуждение -> выбор), "
        "но без длинных монологов и без реплик-титров в кадре. "
        "Верни один JSON с ключами scenes, transitions, keyframes, frame_selection. "
        "frame_selection: массив {frame_index, selected, reason}; для selected=true reason обязателен. "
        "Учитывай, что аудио генерируется отдельным native-audio потоком по выбранным сегментам. "
        "Работай только по текстовому JSON-контракту (id/prompt/метаданные), без inline image bytes/base64."
    )


def lite_transitions_wan26_system_prompt() -> str:
    raw = (read_dream_pipeline_lite_transitions_wan26_raw() or "").strip()
    if raw:
        return raw
    return (
        "План монтажа для wan_2_6_single_anchor: первый keyframe — старт сцены, остальные keyframes — опорные anchors "
        "внутри продолжающегося действия. Для каждого keyframe-gap возвращай animate_transition с цельным motion_prompt, "
        "где динамика охватывает до/в момент кадра/после. Верни один JSON с ключами scenes, transitions, keyframes, frame_selection. "
        "frame_selection: массив {frame_index, selected, reason}; для selected=true reason обязателен. "
        "Работай только по text-first JSON-контракту (id/prompt/метаданные), без inline image bytes/base64."
    )


def lite_transitions_kling_reference_system_prompt() -> str:
    raw = (read_dream_pipeline_lite_transitions_kling_ref_raw() or "").strip()
    if raw:
        return raw
    return (
        "План монтажа для kling_v3_reference_motion: сформируй animate_transition для каждого выбранного keyframe, "
        "чтобы каждый ключевой кадр получил отдельный сегмент движения. Для каждого сегмента верни motion_prompt "
        "человеческим языком (без служебных терминов), duration_sec, segment_story. "
        "Референс-кадр используется как визуальный ориентир через reference image, а не как обязательный last frame. "
        "Верни один JSON с ключами scenes, transitions, keyframes, frame_selection. "
        "frame_selection: массив {frame_index, selected, reason}; для selected=true reason обязателен."
    )


def lite_resolve_montage_preset(
    *,
    selected_video_model: str,
    configured_preset: str | None = None,
) -> str:
    preset = str(configured_preset or "").strip().lower()
    if preset in {"default", "seedance", "wan_2_6_single_anchor", "kling_v3_reference_motion"}:
        return preset
    mid = str(selected_video_model or "").strip().lower()
    if "seedance" in mid:
        return "seedance"
    if "kling-v3.0-std" in mid:
        return "kling_v3_reference_motion"
    return "default"


def lite_effective_prompt_mode(
    *,
    prompt_mode: str,
    montage_preset: str,
    audio_required: bool,
) -> tuple[str, str, bool]:
    pm = (prompt_mode or "first_last_frame").strip() or "first_last_frame"
    if pm not in {"first_last_frame", "first_frame_only", "text_only"}:
        pm = "first_last_frame"
    preset = (montage_preset or "default").strip().lower() or "default"
    if preset == "wan_2_6_single_anchor":
        return "first_frame_only", "locked_wan_single_anchor", True
    if preset == "kling_v3_reference_motion":
        return "first_frame_only", "locked_kling_reference_motion", True
    if preset == "seedance" and bool(audio_required):
        return "first_frame_only", "locked_seedance_first_frame_only", True
    return pm, "unlocked_profile_or_form", False


def lite_build_transition_system_prompt(
    *,
    base_prompt: str,
    prompt_mode: str,
    audio_required: bool,
    montage_preset: str,
) -> str:
    pm = (prompt_mode or "first_last_frame").strip() or "first_last_frame"
    mode_hint = (
        "\n\nВидео-режим: first_last_frame (использовать first+last frame)."
        if pm == "first_last_frame"
        else (
            "\n\nВидео-режим: first_frame_only (ориентироваться на first frame; last_frame может отсутствовать)."
            if pm == "first_frame_only"
            else "\n\nВидео-режим: text_only (ориентироваться на текст движения; кадры опциональны)."
        )
    )
    audio_hint = (
        "\n\nАудио-ветка: audio_required=true. Не планируй текст/реплики в изображении; звук отдельным треком."
        if audio_required
        else "\n\nАудио-ветка: silent."
    )
    preset = (montage_preset or "default").strip().lower()
    preset_hint = (
        "\n\nMontage preset: seedance. Для animate_transition указывай segment_mode: pairwise или single_anchor. "
        "В каждом keyframe-gap сегменте обязательно опиши микро-акт целиком (setup -> development -> payoff) "
        "и фазность Early/Mid/Late; не прыгай сразу от старта к финальному состоянию. "
        "Финальный motion_prompt должен оставаться чистым режиссёрским текстом для i2v, без служебных фраз "
        "вида 'Micro-act rule', 'Early phase:' и без длинного пересказа dream_text."
        if preset == "seedance"
        else (
            "\n\nMontage preset: wan_2_6_single_anchor. Следуй отдельному wan26 system prompt: первый keyframe = scene_start, "
            "остальные keyframes = reference anchors внутри той же сцены."
            if preset == "wan_2_6_single_anchor"
            else (
                "\n\nMontage preset: kling_v3_reference_motion. Строй motion_prompt для Kling v3 standard; "
                "reference image используется как визуальный ориентир через input_references, не как обязательный last frame."
                if preset == "kling_v3_reference_motion"
                else "\n\nMontage preset: default."
            )
        )
    )
    schema_hint = (
        "\n\nСтрогий output schema: JSON object с ключами scenes, transitions, keyframes, frame_selection. "
        "frame_selection: [{frame_index:int, selected:bool, reason:str}]. "
        "Для каждого animate_transition поле duration_sec обязательно (секунды клипа). "
        "Для selected=true reason обязателен. "
        "Никогда не ожидай и не запрашивай binary/base64 изображения: вход только text-first JSON. "
        "Текст motion_prompt должен быть естественным режиссёрским описанием действия; "
        "не используй внутри motion_prompt слова keyframe, anchor, segment_mode и служебные id."
    )
    atmosphere_hint = (
        "\n\nАтмосфера и ритм сцены: сцены должны восприниматься как сон, а не как документальная фиксация событий. "
        "Избегай клипового монтажа, резкой динамики и ощущения музыкального видео. "
        "Предпочтительны длинные текучие наблюдательные движения камеры, плавные переходы внимания и ощущение непрерывного пространства. "
        "Сохраняй лёгкую дымку, мягкое рассеянное освещение, ощущение воздуха и глубины, замедленное субъективное восприятие времени, "
        "странную, но естественную логику сна. Камера должна не просто показывать действие, а наблюдать за пространством и состоянием персонажей. "
        "Во многих сценах движение может быть минимальным: взгляд, поворот головы, ветер, снег, медленный подход, пауза, ожидание. "
        "Не перегружай сцену событиями: лучше меньше действий, но больше ощущения присутствия внутри сна. "
        "Сохраняй ощущение сюрреализма, тревожной тишины, мягкой кинематографичности, медленного течения времени и визуальной поэзии сна."
    )
    return ((base_prompt or "").strip() + mode_hint + audio_hint + preset_hint + schema_hint + atmosphere_hint).strip()


_LITE_TRANSITION_FIELD_CAP = 8000
_LITE_DURATION_MIN_SEC = 1
_LITE_DURATION_MAX_SEC = 15
_LITE_DURATION_DEFAULT_SEC = 5


def _lite_transition_trim(s: str, cap: int = _LITE_TRANSITION_FIELD_CAP) -> str:
    t = (s or "").strip()
    if len(t) <= cap:
        return t
    return t[: cap - 3] + "…"


def _lite_normalize_duration_sec(raw: Any, *, default_sec: int | None = None) -> int | None:
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = 0
    if val <= 0:
        if default_sec is None:
            return None
        val = int(default_sec)
    return max(_LITE_DURATION_MIN_SEC, min(val, _LITE_DURATION_MAX_SEC))


_LITE_PHASE_MARKERS: tuple[str, ...] = (
    "early phase",
    "mid phase",
    "late phase",
    "ранняя фаза",
    "средняя фаза",
    "поздняя фаза",
)
_LITE_PROGRESS_MARKERS: tuple[str, ...] = (
    "затем",
    "потом",
    "после этого",
    "далее",
    "then",
    "after that",
    "next",
    "->",
    "→",
)
_LITE_LOW_SIGNAL_MOTION_MARKERS: tuple[str, ...] = (
    "плавное движение между ключами; развитие сцены по текстам кадров.",
    "плавное движение между ключевыми кадрами",
)
_LITE_SERVICE_TAIL_PATTERNS: tuple[str, ...] = (
    r"Early phase:[\s\S]*?Late phase:[^\n]*",
    r"Micro-act rule:[^\n]*",
    r"setup\s*->\s*development\s*->\s*payoff[^\n]*",
)


def _lite_has_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    low = str(text or "").strip().lower()
    if not low:
        return False
    return any(m in low for m in markers)


def _lite_is_low_signal_motion_prompt(text: str) -> bool:
    low = str(text or "").strip().lower()
    if not low:
        return True
    if low in {m.lower() for m in _LITE_LOW_SIGNAL_MOTION_MARKERS}:
        return True
    return any(m.lower() in low for m in _LITE_LOW_SIGNAL_MOTION_MARKERS)


def _lite_clean_motion_prompt_text(text: str, *, cap: int = 800) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    for pat in _LITE_SERVICE_TAIL_PATTERNS:
        s = re.sub(pat, "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bСюжет сегмента:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return _lite_transition_trim(s, cap)


def _lite_sanitize_i2v_motion_prompt(text: str, *, cap: int = 5000) -> str:
    s = _lite_strip_role_brackets(_lite_humanize_scene_text(_lite_clean_motion_prompt_text(text, cap=cap)))
    if not s:
        return ""
    banned_patterns: tuple[str, ...] = (
        r"Целевой keyframe:?[^\.\n]*\.?",
        r"Роль кадра:?[^\.\n]*\.?",
        r"Тип движения:?[^\.\n]*\.?",
        r"Путь по промежуточным кадрам:?[^\.\n]*\.?",
        r"\bцелевой\s*:?[^\.\n]*\.?",
        r"\bkeyframe\b",
        r"\banchor\b",
        r"\bsegment_mode\b",
        r"cinematic still",
        r"зафиксированный момент",
        r"До этого момента",
        r"Действие непрерывно продолжается",
        r"Во взаимодействии героев",
        r"Сохраняется атмосфера сна",
        r"\bСейчас\b",
        r"\bДальше\b",
        r"Плавный переход между опорными кадрами",
        r"сквозное развитие",
        r"\bэтап\b",
        r"\bшаг\b",
        r"(?<!\w)\d+\s*:\s*",
    )
    for pat in banned_patterns:
        s = re.sub(pat, "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(главный герой|мужчина|дети|девочки)\s+и\s+\1\b", r"\1", s, flags=re.IGNORECASE)
    s = re.sub(r"[,:;]\s*(?=[,.;]|$)", "", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip(" .\n\t")
    return _lite_transition_trim(s, cap)


def _lite_strip_role_brackets(text: str) -> str:
    s = str(text or "")
    if not s:
        return ""
    s = re.sub(
        r"\((?:[^)]*(?:dreamer|child[_\-\s]*\d|close[_\-\s]*man)[^)]*)\)",
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s


def _lite_cleanup_human_phrase(text: str) -> str:
    s = _lite_strip_role_brackets(_lite_humanize_scene_text(text))
    if not s:
        return ""
    # Убираем дубли вида "дети и дети", "мужчина и мужчина"
    s = re.sub(
        r"\b(главный герой|мужчина|дети|девочки)\s+и\s+\1\b",
        r"\1",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s{2,}", " ", s).strip(" ,.;")
    return s


def _lite_extract_action_clauses(text: str) -> list[str]:
    s = _lite_cleanup_human_phrase(text)
    if not s:
        return []
    # Нумерованные куски "1: ... -> 2: ..." распаковываем в отдельные действия.
    numbered = re.findall(r"\b\d+\s*:\s*([^>\n]+)", s)
    if numbered:
        return [_lite_transition_trim(x.strip(), 260) for x in numbered if x.strip()]
    chunks = re.split(r"(?:->|[.;\n]|,\s+затем\s+|,\s+после\s+этого\s+)", s, flags=re.IGNORECASE)
    out: list[str] = []
    for ch in chunks:
        c = _lite_transition_trim(ch.strip(), 260)
        if len(c) < 6:
            continue
        out.append(c)
    return out


def _lite_is_interaction_action(text: str) -> bool:
    low = str(text or "").lower()
    if not low:
        return False
    markers = (
        "прос",
        "обсуж",
        "говор",
        "подход",
        "помог",
        "переда",
        "даёт",
        "дает",
        "берет",
        "берёт",
        "оплат",
        "деньг",
        "диалог",
        "вместе",
    )
    return any(m in low for m in markers)


def _lite_duration_from_actions(*texts: str) -> int:
    score = 0
    seen: set[str] = set()
    for blob in texts:
        for clause in _lite_extract_action_clauses(blob):
            key = clause.lower()
            if key in seen:
                continue
            seen.add(key)
            score += 2 if _lite_is_interaction_action(clause) else 1
    if score <= 0:
        score = 3
    return max(3, min(score, 6))


def _lite_compose_continuous_scene_prompt(
    *,
    is_scene_start: bool,
    dream_ctx: str,
    camera_line: str,
    before_text: str,
    moment_text: str,
    after_text: str,
    intermediate_text: str,
    dialog_hint: str,
) -> str:
    parts: list[str] = []
    cam = _lite_cleanup_human_phrase(camera_line)
    ctx = _lite_cleanup_human_phrase(dream_ctx)
    before = _lite_cleanup_human_phrase(before_text)
    moment = _lite_cleanup_human_phrase(moment_text)
    after = _lite_cleanup_human_phrase(after_text)
    inter = _lite_cleanup_human_phrase(intermediate_text)
    dialog = _lite_cleanup_human_phrase(dialog_hint)

    if is_scene_start:
        if moment:
            parts.append(f"Сцена начинается с того, что {moment}")
    else:
        if before:
            parts.append(before)
        if moment:
            parts.append(moment)
    if inter:
        parts.append(inter)
    if dialog:
        parts.append(dialog)
    if after:
        parts.append(after)
    if cam:
        parts.append(cam)
    if ctx:
        parts.append(ctx)

    merged = ". ".join(p.strip(" .") for p in parts if p.strip())
    return _lite_sanitize_i2v_motion_prompt(merged, cap=5000)


def lite_sanitize_i2v_text_prompt(text: str, *, cap: int = 5000) -> str:
    return _lite_sanitize_i2v_motion_prompt(text, cap=cap)


def _lite_build_unified_i2v_prompt(
    *,
    dream_text: str,
    image_prompt: str,
    motion_prompt: str,
    target_keyframe: int | None = None,
) -> str:
    _ = dream_text
    _ = image_prompt
    _ = target_keyframe
    motion = _lite_sanitize_i2v_motion_prompt(str(motion_prompt or "").strip(), cap=5000)
    return motion


def lite_sanitize_animation_markup_for_i2v(animation_markup: dict[str, Any] | None) -> dict[str, Any]:
    """Нормализует сегменты для UI/step5, чтобы в i2v prompt не попадала служебная лексика."""
    if not isinstance(animation_markup, dict):
        return {}
    out = dict(animation_markup)
    lines_out: list[dict[str, Any]] = []
    for line in list(out.get("lines") or []):
        if not isinstance(line, dict):
            continue
        line_copy = dict(line)
        segs_out: list[dict[str, Any]] = []
        for seg in list(line.get("segments") or []):
            if not isinstance(seg, dict):
                continue
            s = dict(seg)
            payload = (
                dict(s.get("api_payload_preview") or {})
                if isinstance(s.get("api_payload_preview"), dict)
                else {}
            )
            prompt_candidates = [
                str(payload.get("prompt") or "").strip(),
                str(s.get("final_prompt") or "").strip(),
                str(s.get("motion_prompt_suggested") or "").strip(),
                str(s.get("motion_prompt_preview") or "").strip(),
            ]
            clean_prompt = ""
            for cand in prompt_candidates:
                clean_prompt = _lite_sanitize_i2v_motion_prompt(cand, cap=5000)
                if clean_prompt:
                    break
            s["motion_prompt_suggested"] = clean_prompt
            s["motion_prompt_preview"] = _lite_transition_trim(clean_prompt, 260)
            s["final_prompt"] = clean_prompt
            payload["prompt"] = clean_prompt
            payload["motion_prompt"] = clean_prompt
            if "image_prompt" in payload:
                payload["image_prompt"] = ""
            s["api_payload_preview"] = payload
            segs_out.append(s)
        line_copy["segments"] = segs_out
        lines_out.append(line_copy)
    out["lines"] = lines_out
    return out


def _lite_bridge_text_for_gap(
    fi: int,
    ti: int,
    by_idx_map: dict[int, dict[str, Any]],
    *,
    max_items: int = 4,
) -> str:
    if ti - fi <= 1:
        return ""
    parts: list[str] = []
    for ix in range(fi + 1, ti):
        mid = by_idx_map.get(ix) or {}
        step = _lite_transition_trim(str(mid.get("izmenenie") or mid.get("kad") or "").strip(), 140)
        if step:
            parts.append(step)
        if len(parts) >= max_items:
            break
    if not parts:
        return "Развивай действие непрерывно до следующего важного момента без резкого скачка."
    return " ".join(parts)


def _lite_gap_path_summary(
    fi: int,
    ti: int,
    by_idx_map: dict[int, dict[str, Any]],
    *,
    max_items: int = 12,
) -> str:
    if ti - fi <= 1:
        return "Действие продолжается без промежуточных развилок."
    parts: list[str] = []
    for ix in range(fi + 1, ti):
        mid = by_idx_map.get(ix) or {}
        beat = _lite_transition_trim(
            str(mid.get("izmenenie") or mid.get("kad") or mid.get("opora") or "").strip(),
            180,
        )
        if beat:
            parts.append(beat)
        else:
            parts.append("Удерживай непрерывное действие без резкого скачка.")
        if len(parts) >= max_items:
            break
    return " ".join(parts)


def _lite_dialog_hint_for_gap(fi: int, ti: int, by_idx_map: dict[int, dict[str, Any]]) -> str:
    if ti - fi <= 1:
        return ""
    blob_parts: list[str] = []
    for ix in range(fi + 1, ti):
        mid = by_idx_map.get(ix) or {}
        blob_parts.append(str(mid.get("izmenenie") or ""))
        blob_parts.append(str(mid.get("kad") or ""))
    blob = " ".join(blob_parts).lower()
    if not blob.strip():
        return ""
    has_request = any(x in blob for x in ("прос", "куп", "заказ"))
    has_discuss = any(x in blob for x in ("обсуж", "уточ", "соглас", "очеред"))
    has_choice = any(x in blob for x in ("выбор", "выбира", "оплат", "касс", "деньг"))
    if has_request and has_discuss and has_choice:
        return "Герои договариваются о покупке, уточняют детали и завершают оплату."
    if has_request and has_choice:
        return "Герои обмениваются просьбой и быстро переходят к выбору перед оплатой."
    return ""


def _lite_enforce_phase_microact_contract(
    motion_prompt: str,
    segment_story: str,
) -> tuple[str, str, bool, bool]:
    motion = _lite_clean_motion_prompt_text(motion_prompt)
    story = str(segment_story or "").strip()
    blob = f"{motion}\n{story}".strip()
    has_phase = _lite_has_any_marker(blob, _LITE_PHASE_MARKERS)
    has_progress = _lite_has_any_marker(blob, _LITE_PROGRESS_MARKERS)
    micro_act_applied = False
    if not has_phase:
        phase_tail = (
            "Ранняя фаза: завязка и контекст, без поздно вводимых объектов. "
            "Средняя фаза: развитие действия через промежуточные такты, без прыжка к финалу. "
            "Поздняя фаза: payoff рядом с целевым keyframe; поздние объекты появляются только здесь."
        )
        story = _lite_transition_trim(f"{story} {phase_tail}".strip(), 400) if story else _lite_transition_trim(phase_tail, 400)
        has_phase = True
        micro_act_applied = True
    if not has_progress:
        progress_tail = (
            "Микро-акт: setup -> development -> payoff; покрыть промежуточные сюжетные такты "
            "до target keyframe и не прыгать сразу в финальное состояние."
        )
        story = _lite_transition_trim(f"{story} {progress_tail}".strip(), 400) if story else _lite_transition_trim(progress_tail, 400)
        micro_act_applied = True
    return _lite_clean_motion_prompt_text(motion), story, has_phase, micro_act_applied


def _lite_humanize_scene_text(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    repls: list[tuple[str, str]] = [
        (r"\bdreamer\b", "главный герой"),
        (r"\bchild[_\-\s]*1\b", "дети"),
        (r"\bchild[_\-\s]*2\b", "дети"),
        (r"\bclose[_\-\s]*man\b", "знакомый мужчина"),
    ]
    out = s
    for pat, val in repls:
        out = re.sub(pat, val, out, flags=re.IGNORECASE)
    return out.strip()


def _lite_payload_image_url_for_llm(row: dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    urls = list(row.get("urls") or [])
    raw = str(urls[0]).strip() if urls else ""
    safe = _lite_safe_image_href_for_montage_metadata(raw)
    return str(safe or "").strip()


def lite_transitions_user_payload_dict(
    *,
    dream_text: str,
    env_cards: list[dict[str, Any]],
    char_cards: list[dict[str, Any]],
    generated_frames: list[dict[str, Any]],
    montage_preset: str = "default",
) -> dict[str, Any]:
    """
    Минимальный user payload для LLM шага 4: только человеко-понятные поля.
    Внутренние runtime поля и id сохраняются в системе, но не отправляются в LLM.
    """
    _ = env_cards
    _ = char_cards
    _ = montage_preset
    frames_out: list[dict[str, Any]] = []
    for j, row in enumerate(generated_frames):
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if idx is None:
            idx = j
        is_keyframe = bool(row.get("is_keyframe", True))
        frame_row: dict[str, Any] = {
            "index": int(idx),
            "is_keyframe": is_keyframe,
            "description": _lite_transition_trim(
                _lite_humanize_scene_text(str(row.get("kad") or "").strip()),
                1200,
            ),
            "change": _lite_transition_trim(
                _lite_humanize_scene_text(
                    str(row.get("izmenenie") or row.get("delta") or "").strip()
                ),
                1200,
            ),
        }
        image_url = _lite_payload_image_url_for_llm(row)
        if is_keyframe and image_url:
            frame_row["image_url"] = image_url
        frames_out.append(frame_row)
    frames_out.sort(key=lambda x: int(x["index"]))
    return {
        "dream_text": _lite_transition_trim(_lite_humanize_scene_text(str(dream_text or "")), 12000),
        "frames": frames_out,
    }


def _lite_safe_image_href_for_montage_metadata(url: str | None) -> str | None:
    """Короткий URL для JSON шага 4: без гигантских data URI (ломают форму и разметку)."""
    s = (url or "").strip()
    if not s or s.lower().startswith("data:"):
        return None
    if len(s) > 4096:
        return None
    return s


def _lite_image_id_for_montage_metadata(index: int, image_href: str | None) -> str:
    href = (image_href or "").strip()
    if href:
        tail = href.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        if tail:
            stem = tail.rsplit(".", 1)[0]
            sid = _lite_sanitize_basename(stem)[:80]
            if sid:
                return sid
    return f"frame_{int(index):03d}"


def lite_frames_metadata_for_montage_form(
    generated_frames: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Компактные метаданные кадров для скрытого поля шага 4 (без data URI / длинных URL).
    При необходимости добавляет image_href — только http(s) или относительные короткие пути.
    """
    out: list[dict[str, Any]] = []
    for j, row in enumerate(generated_frames or []):
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if idx is None:
            idx = j
        urls = list(row.get("urls") or [])
        explicit_img_ok = row.get("image_generated_ok")
        if explicit_img_ok is not None:
            image_gen_ok = bool(explicit_img_ok)
        else:
            image_gen_ok = bool(row.get("ok") and urls and any(str(u).strip() for u in urls))
        u0 = str(urls[0]).strip() if urls else ""
        image_href = _lite_safe_image_href_for_montage_metadata(u0)
        item: dict[str, Any] = {
            "index": int(idx),
            "image_id": str(row.get("image_id") or "").strip() or _lite_image_id_for_montage_metadata(int(idx), image_href),
            "title": str(row.get("title") or "").strip(),
            "opora": str(row.get("opora") or "").strip(),
            "izmenenie": str(row.get("izmenenie") or "").strip(),
            "kad": str(row.get("kad") or "").strip(),
            "img_prompt": str(row.get("img_prompt") or "").strip(),
            "base_reference": str(row.get("base_reference") or "").strip(),
            "character_references": list(row.get("character_references") or []),
            "use_previous_frame": row.get("use_previous_frame"),
            "use_previous_frame_resolved": row.get("use_previous_frame_resolved"),
            "forced_prev_chain_break": row.get("forced_prev_chain_break"),
            "is_keyframe": bool(row.get("is_keyframe", True)),
            "keyframe_reason": str(row.get("keyframe_reason") or "").strip(),
            "ok": bool(row.get("ok") or image_gen_ok),
            "image_generated_ok": image_gen_ok,
            "generation_status": str(row.get("generation_status") or ("generated" if image_gen_ok else "unknown")),
        }
        if image_href:
            item["image_href"] = image_href
        out.append(item)
    out.sort(key=lambda x: int(x["index"]))
    return out


def lite_frames_from_montage_form_metadata(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Восстановить generated_frames для lite_compute_transition_plan из JSON шага 4."""
    out: list[dict[str, Any]] = []
    for j, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if idx is None:
            idx = j
        href = (row.get("image_href") or "").strip()
        item: dict[str, Any] = {
            "index": int(idx),
            "image_id": str(row.get("image_id") or "").strip() or _lite_image_id_for_montage_metadata(int(idx), href),
            "title": str(row.get("title") or "").strip(),
            "opora": str(row.get("opora") or "").strip(),
            "izmenenie": str(row.get("izmenenie") or "").strip(),
            "kad": str(row.get("kad") or "").strip(),
            "img_prompt": str(row.get("img_prompt") or "").strip(),
            "base_reference": str(row.get("base_reference") or "").strip(),
            "character_references": list(row.get("character_references") or []),
            "use_previous_frame": row.get("use_previous_frame"),
            "use_previous_frame_resolved": row.get("use_previous_frame_resolved"),
            "forced_prev_chain_break": row.get("forced_prev_chain_break"),
            "is_keyframe": bool(row.get("is_keyframe", True)),
            "keyframe_reason": str(row.get("keyframe_reason") or "").strip(),
            "ok": bool(row.get("ok", True)),
            "urls": [href] if href else [],
            "image_generated_ok": row.get("image_generated_ok"),
            "generation_status": str(row.get("generation_status") or ""),
        }
        if href:
            item["image_href"] = href
        if item.get("image_generated_ok") is None:
            item["image_generated_ok"] = bool(item["ok"])
        out.append(item)
    out.sort(key=lambda x: int(x["index"]))
    return out


def lite_first_frame_stored_image_url(frame: dict[str, Any]) -> str | None:
    """
    Первый URL кадра как в Mongo/статике (/dev/static/... или https://).
    Без чтения файла и без base64 — для UI и JSON; перед video/OpenRouter вызывайте
    lite_resolve_image_url_for_external_api.
    """
    if not isinstance(frame, dict):
        return None
    frame_ok = bool(frame.get("ok") or frame.get("image_generated_ok"))
    if not frame_ok:
        return None
    urls = list(frame.get("urls") or [])
    if not urls:
        return None
    u = str(urls[0]).strip()
    return u or None


def lite_first_frame_image_url(frame: dict[str, Any]) -> str | None:
    """Совместимость: то же, что lite_first_frame_stored_image_url."""
    return lite_first_frame_stored_image_url(frame)


def lite_motion_prompt_for_prev_segment(
    *,
    dream_text: str,
    f0: dict[str, Any],
    f1: dict[str, Any],
    transition_plan: dict[str, Any] | None,
    from_index: int,
    to_index: int,
) -> tuple[str, str]:
    """
    Черновик motion_prompt для пары кадров на prev-линии: сначала план монтажа (LLM),
    иначе развёрнутый fallback из kad/izmenenie + усечённый текст сна.
    Возвращает (текст, метка источника для UI).
    """
    plan_mp = lite_motion_prompt_from_transition_plan(transition_plan, from_index, to_index)
    if plan_mp:
        return _lite_clean_motion_prompt_text(_lite_transition_trim(plan_mp, 4000)), "transition_plan"
    iz = _lite_transition_trim(str(f1.get("izmenenie") or "").strip(), 200)
    kad0 = _lite_transition_trim(str(f0.get("kad") or "").strip(), 120)
    kad1 = _lite_transition_trim(str(f1.get("kad") or "").strip(), 120)
    op0 = str(f0.get("opora") or "").strip()
    op1 = str(f1.get("opora") or "").strip()
    clauses: list[str] = []
    if iz:
        clauses.append(f"Ключевой визуальный сдвиг: {iz}.")
    elif kad0 or kad1:
        clauses.append(f"Переход от кадра «{kad0 or '…'}» к «{kad1 or '…'}».")
    elif op1 or op0:
        clauses.append(
            f"Опора сцены: {_lite_transition_trim(op1 or op0, 120)}. Сохранить свет, перспективу и стиль."
        )
    if not clauses:
        return (
            "Плавное движение между ключами, та же сцена и свет.",
            "default",
        )
    motion = " ".join(clauses)
    return _lite_clean_motion_prompt_text(_lite_transition_trim(motion, 4000)), "frame_text"


def lite_collect_animate_i2v_segments(
    transition_plan: dict[str, Any] | None,
    generated_frames: list[dict[str, Any]],
    *,
    dream_text: str = "",
    prompt_mode: str = "first_last_frame",
    montage_preset: str = "default",
    audio_required: bool = False,
    scene_segment_stride: int = 1,
    reference_frame_stride: int = 1,
) -> list[dict[str, Any]]:
    """Сегменты Wan i2v: только animate_transition, с start/end URL из сгенерированных кадров."""
    plan = transition_plan or {}
    mm = str(plan.get("montage_mode") or "").strip().lower()
    # Разрежённый план от LLM — не применять stride (иначе конфликт двух источников истины).
    if mm == "sparse":
        reference_frame_stride = 1
        scene_segment_stride = 1

    trans = list(plan.get("transitions") or [])
    trans.sort(key=lambda x: int(x.get("from_frame_index", 0)))

    def _frame_has_runtime_image(row: dict[str, Any]) -> bool:
        explicit = row.get("image_generated_ok")
        if explicit is not None:
            return bool(explicit) and bool(lite_first_frame_image_url(row))
        return bool(row.get("ok")) and bool(lite_first_frame_image_url(row))

    by_idx: dict[int, dict[str, Any]] = {}
    for j, f in enumerate(generated_frames):
        if not isinstance(f, dict):
            continue
        ix = f.get("index")
        if ix is None:
            ix = j
        by_idx[int(ix)] = f

    out: list[dict[str, Any]] = []
    pm, pm_policy, pm_locked = lite_effective_prompt_mode(
        prompt_mode=prompt_mode,
        montage_preset=montage_preset,
        audio_required=audio_required,
    )
    kling_ref_mode = (str(montage_preset or "").strip().lower() == "kling_v3_reference_motion")
    preset = str(montage_preset or "default").strip().lower() or "default"
    if preset in {"wan_2_6_single_anchor", "kling_v3_reference_motion"}:
        is_kling = preset == "kling_v3_reference_motion"
        dream_ctx = _lite_transition_trim(
            _lite_humanize_scene_text(
                str(dream_text or "").strip() or "Сохраняй атмосферу исходного сна и непрерывность одной сцены."
            ),
            260,
        )
        keyframes: list[int] = []
        selected_keyframes: list[int] = []
        for row in list(plan.get("frame_selection") or []):
            if not isinstance(row, dict):
                continue
            if not bool(row.get("selected")):
                continue
            try:
                s_ix = int(row.get("frame_index"))
            except (TypeError, ValueError):
                continue
            if s_ix in by_idx and s_ix not in selected_keyframes:
                selected_keyframes.append(s_ix)
        for raw in list(plan.get("keyframes") or []):
            try:
                ix = int(raw)
            except (TypeError, ValueError):
                continue
            if ix in by_idx and ix not in keyframes:
                keyframes.append(ix)
        if selected_keyframes:
            for s_ix in selected_keyframes:
                if s_ix not in keyframes:
                    keyframes.append(s_ix)
        if not keyframes:
            for ix, row in sorted(by_idx.items()):
                if bool(row.get("is_keyframe")) and _frame_has_runtime_image(row):
                    keyframes.append(int(ix))
        if is_kling and len(keyframes) < 2:
            keyframes = sorted(ix for ix, row in by_idx.items() if _frame_has_runtime_image(row))
        if not keyframes:
            keyframes = sorted(ix for ix, row in by_idx.items() if _frame_has_runtime_image(row))
        if keyframes:
            first = min(keyframes)
            if first != 0 and 0 in by_idx and _frame_has_runtime_image(by_idx.get(0) or {}):
                keyframes.insert(0, 0)
        keyframes = sorted(set(keyframes))
        if pm != "text_only":
            keyframes = [ix for ix in keyframes if _frame_has_runtime_image(by_idx.get(ix) or {})]
        if is_kling and len(keyframes) < 2:
            keyframes = sorted(ix for ix, row in by_idx.items() if _frame_has_runtime_image(row))
        tr_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
        for t in trans:
            if str(t.get("transition_type") or "") != "animate_transition":
                continue
            try:
                fi = int(t.get("from_frame_index"))
                ti = int(t.get("to_frame_index"))
            except (TypeError, ValueError):
                continue
            tr_by_pair[(fi, ti)] = t
        for i, kx in enumerate(keyframes):
            row = by_idx.get(kx) or {}
            u0 = lite_first_frame_image_url(row)
            if pm != "text_only" and not u0:
                continue
            prev_k = int(keyframes[i - 1]) if i > 0 else None
            next_k = int(keyframes[i + 1]) if i + 1 < len(keyframes) else None
            target_keyframe = next_k if next_k is not None else kx
            before_plan = ""
            after_plan = ""
            if prev_k is not None:
                before_plan = _lite_clean_motion_prompt_text(
                    str((tr_by_pair.get((prev_k, kx)) or {}).get("motion_prompt") or "").strip()
                )
            if next_k is not None:
                after_plan = _lite_clean_motion_prompt_text(
                    str((tr_by_pair.get((kx, next_k)) or {}).get("motion_prompt") or "").strip()
                )
            pre_beats = (
                _lite_humanize_scene_text(_lite_bridge_text_for_gap(prev_k, kx, by_idx, max_items=8))
                if prev_k is not None
                else "Действие начинается из текущего состояния сцены и развивается вперёд."
            )
            post_beats = (
                _lite_humanize_scene_text(_lite_bridge_text_for_gap(kx, next_k, by_idx, max_items=12))
                if next_k is not None
                else "Действие постепенно затихает без резкого обрыва."
            )
            gap_path_summary = _lite_humanize_scene_text(
                _lite_gap_path_summary(kx, target_keyframe, by_idx, max_items=12)
            )
            dialog_before = (
                _lite_humanize_scene_text(_lite_dialog_hint_for_gap(prev_k, kx, by_idx))
                if prev_k is not None
                else ""
            )
            dialog_after = (
                _lite_humanize_scene_text(_lite_dialog_hint_for_gap(kx, next_k, by_idx))
                if next_k is not None
                else ""
            )
            in_frame_src = (
                str(row.get("kad") or row.get("opora") or row.get("izmenenie") or "").strip()
                if i == 0
                else str(row.get("izmenenie") or row.get("kad") or row.get("opora") or "").strip()
            )
            in_frame = _lite_transition_trim(_lite_humanize_scene_text(in_frame_src), 260)
            role = "scene_start" if i == 0 else "central_moment"
            camera_line = (
                "Камера мягко приближается к действию и удерживает внимание на героях."
                if i == 0
                else "Камера следует за действием без резких рывков, сохраняя непрерывность сцены."
            )
            before_line = _lite_humanize_scene_text(before_plan or pre_beats)
            after_line = _lite_humanize_scene_text(after_plan or post_beats)
            dialog_hint = (
                dialog_before
                if dialog_before and dialog_before == dialog_after
                else " ".join([x for x in [dialog_before, dialog_after] if x]).strip()
            )
            motion = _lite_compose_continuous_scene_prompt(
                is_scene_start=bool(i == 0),
                dream_ctx=dream_ctx,
                camera_line=camera_line,
                before_text=before_line,
                moment_text=in_frame or "действие продолжается без остановки",
                after_text=after_line,
                intermediate_text=gap_path_summary,
                dialog_hint=dialog_hint,
            )
            story_parts = [
                (
                    "Сегмент начинает сцену и ведёт действие вперёд."
                    if i == 0
                    else "Сегмент фиксирует важный момент внутри продолжающейся сцены."
                )
            ]
            if prev_k is not None:
                story_parts.append(f"pre_anchor_beats: {pre_beats}")
            story_parts.append(f"anchor_frame_state: {in_frame or 'сохраняется визуальная опора keyframe'}")
            story_parts.append(f"post_anchor_beats: {post_beats}")
            story_parts.append(f"target_keyframe: {target_keyframe}")
            story_parts.append(f"gap_path: {gap_path_summary}")
            segment_story = _lite_transition_trim(" ".join(story_parts), 400)
            duration_sec = None
            src_tr = tr_by_pair.get((kx, next_k)) if next_k is not None else None
            if src_tr is None and prev_k is not None:
                src_tr = tr_by_pair.get((prev_k, kx))
            duration_sec = _lite_duration_from_actions(
                str(row.get("izmenenie") or ""),
                before_line,
                in_frame,
                after_line,
                gap_path_summary,
                dialog_hint,
            )
            final_prompt = _lite_build_unified_i2v_prompt(
                dream_text=dream_text,
                image_prompt=str(row.get("img_prompt") or "").strip(),
                motion_prompt=motion,
                target_keyframe=target_keyframe,
            )
            out.append(
                {
                    "from_frame_index": kx,
                    "to_frame_index": next_k if next_k is not None else kx,
                    "motion_prompt": motion,
                    "final_prompt": final_prompt,
                    "image_url": u0 if pm != "text_only" else "",
                    "image_prompt": _lite_transition_trim(str(row.get("img_prompt") or "").strip(), 1200),
                    "last_frame_url": "",
                    "prompt_mode": pm,
                    "effective_prompt_mode": pm,
                    "effective_prompt_policy": pm_policy,
                    "prompt_mode_locked": bool(pm_locked),
                    "montage_preset": preset,
                    "segment_mode": ("reference_motion" if is_kling else "single_anchor"),
                    "duration_sec": (5 if kling_ref_mode else duration_sec),
                    "segment_story": segment_story,
                    "target_keyframe": target_keyframe,
                    "gap_path_summary": gap_path_summary,
                    "voiceover_text": str((src_tr or {}).get("voiceover_text") or "").strip(),
                    "phase_timing_text_present": False,
                    "micro_act_contract_applied": False,
                    "is_scene_start": bool(i == 0),
                    "anchor_role": ("reference_keyframe" if is_kling else role),
                    "pre_anchor_beats": pre_beats if prev_k is not None else "",
                    "anchor_frame_state": in_frame,
                    "post_anchor_beats": post_beats,
                    "reference_image_url": (u0 if kling_ref_mode else ""),
                }
            )
        out.sort(key=lambda x: int(x.get("from_frame_index") or 0))
        return out
    for t in trans:
        if str(t.get("transition_type") or "") != "animate_transition":
            continue
        fi = int(t["from_frame_index"])
        ti = int(t["to_frame_index"])
        seg_mode = str(t.get("segment_mode") or "pairwise").strip().lower().replace("-", "_")
        if seg_mode not in {"pairwise", "single_anchor"}:
            seg_mode = "pairwise"
        f0 = by_idx.get(fi)
        f1 = by_idx.get(ti)
        u0 = lite_first_frame_image_url(f0 or {})
        u1 = lite_first_frame_image_url(f1 or {})
        if pm != "text_only" and not u0:
            continue
        if pm == "first_last_frame" and not u1 and seg_mode != "single_anchor":
            continue
        mp = _lite_clean_motion_prompt_text(str(t.get("motion_prompt") or "").strip()) or "плавное движение между ключевыми кадрами"
        bridge = _lite_bridge_text_for_gap(fi, ti, by_idx)
        dialog_hint = _lite_dialog_hint_for_gap(fi, ti, by_idx)
        if bridge:
            mp = f"{mp}\n\n{bridge}"
        if dialog_hint:
            mp = f"{mp}\n\n{dialog_hint}"
        duration_sec = _lite_normalize_duration_sec(
            t.get("duration_sec"),
            default_sec=_LITE_DURATION_DEFAULT_SEC,
        )
        segment_story = str(t.get("segment_story") or "").strip()
        voiceover_text = str(t.get("voiceover_text") or "").strip()
        if not segment_story and bridge:
            segment_story = bridge
        mp, segment_story, phase_present, micro_applied = _lite_enforce_phase_microact_contract(
            mp,
            segment_story,
        )
        mp = _lite_clean_motion_prompt_text(mp)
        final_prompt = _lite_build_unified_i2v_prompt(
            dream_text=dream_text,
            image_prompt="",
            motion_prompt=mp,
            target_keyframe=ti,
        )
        out.append(
            {
                "from_frame_index": fi,
                "to_frame_index": ti,
                "motion_prompt": mp,
                "final_prompt": final_prompt,
                "image_url": u0 if pm != "text_only" else "",
                "last_frame_url": u1 if pm == "first_last_frame" else "",
                "prompt_mode": pm,
                "effective_prompt_mode": pm,
                "effective_prompt_policy": pm_policy,
                "prompt_mode_locked": bool(pm_locked),
                "montage_preset": preset,
                "segment_mode": seg_mode,
                "duration_sec": (5 if kling_ref_mode else duration_sec),
                "segment_story": segment_story,
                "voiceover_text": voiceover_text,
                "phase_timing_text_present": bool(phase_present),
                "micro_act_contract_applied": bool(t.get("micro_act_contract_applied") or micro_applied),
                "reference_image_url": (u0 if kling_ref_mode else ""),
            }
        )
    rf = max(1, int(reference_frame_stride or 1))
    if rf > 1:
        out = [s for s in out if int(s.get("from_frame_index") or 0) % rf == 0]
    ss = max(1, int(scene_segment_stride or 1))
    if ss > 1:
        out = [out[i] for i in range(0, len(out), ss)]

    # Если план не дал полную рабочую цепочку, достраиваем пары между доступными image-якорями.
    anchors = sorted(ix for ix, row in by_idx.items() if _frame_has_runtime_image(row))
    if len(anchors) >= 2 and not out:
        existing_pairs = {
            (int(s.get("from_frame_index") or 0), int(s.get("to_frame_index") or 0))
            for s in out
            if isinstance(s, dict)
        }
        for i in range(len(anchors) - 1):
            fi, ti = int(anchors[i]), int(anchors[i + 1])
            if (fi, ti) in existing_pairs:
                continue
            f0 = by_idx.get(fi) or {}
            f1 = by_idx.get(ti) or {}
            u0 = lite_first_frame_image_url(f0)
            u1 = lite_first_frame_image_url(f1)
            if pm != "text_only" and not u0:
                continue
            if pm == "first_last_frame" and not u1:
                continue
            bridge = _lite_bridge_text_for_gap(fi, ti, by_idx)
            motion = "Переход между ключевыми изображениями по сюжетной дуге."
            if bridge:
                motion = f"{motion}\n\n{bridge}"
            dialog_hint = _lite_dialog_hint_for_gap(fi, ti, by_idx)
            if dialog_hint:
                motion = f"{motion}\n\n{dialog_hint}"
            motion, segment_story_fb, phase_present_fb, micro_applied_fb = _lite_enforce_phase_microact_contract(
                motion,
                bridge,
            )
            motion = _lite_clean_motion_prompt_text(motion)
            final_prompt = _lite_build_unified_i2v_prompt(
                dream_text=dream_text,
                image_prompt="",
                motion_prompt=motion,
                target_keyframe=ti,
            )
            out.append(
                {
                    "from_frame_index": fi,
                    "to_frame_index": ti,
                    "motion_prompt": motion,
                    "final_prompt": final_prompt,
                    "image_url": u0 if pm != "text_only" else "",
                    "last_frame_url": u1 if pm == "first_last_frame" else "",
                    "prompt_mode": pm,
                    "effective_prompt_mode": pm,
                    "effective_prompt_policy": pm_policy,
                    "prompt_mode_locked": bool(pm_locked),
                    "montage_preset": preset,
                    "segment_mode": "pairwise",
                    "duration_sec": (5 if kling_ref_mode else _LITE_DURATION_DEFAULT_SEC),
                    "segment_story": segment_story_fb,
                    "voiceover_text": "",
                    "phase_timing_text_present": bool(phase_present_fb),
                    "micro_act_contract_applied": bool(micro_applied_fb),
                    "reference_image_url": (u0 if kling_ref_mode else ""),
                }
            )
    out.sort(key=lambda x: (int(x.get("from_frame_index") or 0), int(x.get("to_frame_index") or 0)))
    return out


def lite_motion_prompt_from_transition_plan(
    transition_plan: dict[str, Any] | None,
    from_index: int,
    to_index: int,
) -> str:
    """Текст animate_transition из плана монтажа для пары кадров, если есть."""
    plan = transition_plan or {}
    for t in plan.get("transitions") or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("transition_type") or "") != "animate_transition":
            continue
        try:
            fi = int(t.get("from_frame_index"))
            ti = int(t.get("to_frame_index"))
        except (TypeError, ValueError):
            continue
        if fi == from_index and ti == to_index:
            mp = str(t.get("motion_prompt") or "").strip()
            if _lite_is_low_signal_motion_prompt(mp):
                return ""
            return _lite_clean_motion_prompt_text(mp)
    return ""


def lite_build_prev_line_animation_markup(
    *,
    dream_text: str,
    generated_frames: list[dict[str, Any]],
    transition_plan: dict[str, Any] | None = None,
    prompt_mode: str = "first_last_frame",
    montage_preset: str = "default",
    audio_required: bool = False,
) -> dict[str, Any]:
    """
    Разметка для будущей анимации: только пары кадров внутри одной «линии» prev.
    Между линиями наследование last_frame предыдущего клипа не предполагается.
    Автоматический вызов i2v не выполняется — только структура и черновик промпта для UI.
    """
    rows = [f for f in (generated_frames or []) if isinstance(f, dict)]
    rows.sort(key=lambda r: int(r.get("index") if r.get("index") is not None else 0))
    pm, pm_policy, pm_locked = lite_effective_prompt_mode(
        prompt_mode=prompt_mode,
        montage_preset=montage_preset,
        audio_required=audio_required,
    )
    kling_ref_mode = (str(montage_preset or "").strip().lower() == "kling_v3_reference_motion")
    dream_excerpt = _lite_transition_trim((dream_text or "").strip(), 600)
    if not rows:
        return {
            "dream_text_excerpt": dream_excerpt,
            "lines": [],
            "line_boundaries": [],
            "n_frames": 0,
        }

    by_idx: dict[int, dict[str, Any]] = {}
    for f in rows:
        ix = f.get("index")
        if ix is None:
            continue
        by_idx[int(ix)] = f

    edge_set = lite_plan_animate_edge_set(transition_plan)
    mm = str((transition_plan or {}).get("montage_mode") or "").strip().lower()
    tr_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    for tr in list((transition_plan or {}).get("transitions") or []):
        if not isinstance(tr, dict):
            continue
        if str(tr.get("transition_type") or "").strip() != "animate_transition":
            continue
        try:
            fi = int(tr.get("from_frame_index"))
            ti = int(tr.get("to_frame_index"))
        except (TypeError, ValueError):
            continue
        tr_by_pair[(fi, ti)] = tr

    keyframes = []
    for x in list((transition_plan or {}).get("keyframes") or []):
        try:
            ix = int(x)
        except (TypeError, ValueError):
            continue
        if ix in by_idx and ix not in keyframes:
            keyframes.append(ix)
    keyframes.sort()

    preset_norm = str(montage_preset or "default").strip().lower() or "default"
    if preset_norm in {"wan_2_6_single_anchor", "kling_v3_reference_motion"}:
        wan_segments = lite_collect_animate_i2v_segments(
            transition_plan or {},
            rows,
            dream_text=dream_text,
            prompt_mode=pm,
            montage_preset=preset_norm,
            audio_required=audio_required,
            scene_segment_stride=1,
            reference_frame_stride=1,
        )
        segs: list[dict[str, Any]] = []
        for j, seg in enumerate(wan_segments):
            fi = int(seg.get("from_frame_index") or 0)
            ti = int(seg.get("to_frame_index") or fi)
            f0 = by_idx.get(fi, {})
            f1 = by_idx.get(ti, {})
            u0 = lite_first_frame_stored_image_url(f0)
            payload_preview: dict[str, Any]
            if preset_norm == "kling_v3_reference_motion":
                ref_u = str(seg.get("reference_image_url") or u0 or "").strip()
                payload_preview = {
                    "prompt": str(seg.get("final_prompt") or seg.get("motion_prompt") or ""),
                    "duration_sec": seg.get("duration_sec"),
                    "size": "720x720",
                    "reference_image_url": ref_u,
                    "input_references": (
                        [{"type": "image_url", "image_url": ref_u}]
                        if ref_u
                        else []
                    ),
                }
            else:
                payload_preview = {
                    "image_url": u0 if pm != "text_only" else "",
                    "prompt": str(seg.get("final_prompt") or seg.get("motion_prompt") or ""),
                    "duration_sec": seg.get("duration_sec"),
                }
            segs.append(
                {
                    "segment_index": j,
                    "from_frame_index": fi,
                    "to_frame_index": ti if pm == "first_last_frame" else fi,
                    "target_frame_index": int(seg.get("target_keyframe") or fi),
                    "from_title": str(f0.get("title") or f"Кадр {fi + 1}").strip(),
                    "to_title": str(f1.get("title") or f"Кадр {ti + 1}").strip(),
                    "image_url_start": u0 if pm != "text_only" else "",
                    "image_prompt": _lite_transition_trim(str(f0.get("img_prompt") or "").strip(), 1200),
                    "image_url_end": "",
                    "both_images_ready": bool(u0) if pm != "text_only" else True,
                    "in_montage_plan": True,
                    "montage_mode": str(seg.get("segment_mode") or "single_anchor"),
                    "montage_preset": str(montage_preset or "default").strip().lower() or "default",
                    "prompt_mode": pm,
                    "effective_prompt_mode": str(seg.get("effective_prompt_mode") or pm),
                    "effective_prompt_policy": str(seg.get("effective_prompt_policy") or pm_policy),
                    "prompt_mode_locked": bool(seg.get("prompt_mode_locked", pm_locked)),
                    "segment_mode": str(seg.get("segment_mode") or "single_anchor"),
                    "duration_sec": seg.get("duration_sec"),
                    "segment_story": str(seg.get("segment_story") or ""),
                    "voiceover_text": str(seg.get("voiceover_text") or ""),
                    "phase_timing_text_present": bool(seg.get("phase_timing_text_present")),
                    "micro_act_contract_applied": bool(seg.get("micro_act_contract_applied")),
                    "motion_prompt_preview": _lite_transition_trim(str(seg.get("motion_prompt") or ""), 260),
                    "motion_prompt_suggested": str(seg.get("motion_prompt") or ""),
                    "final_prompt": str(seg.get("final_prompt") or seg.get("motion_prompt") or ""),
                    "motion_prompt_source": "wan_single_anchor_builder",
                    "is_scene_start": bool(seg.get("is_scene_start")),
                    "anchor_role": str(seg.get("anchor_role") or ""),
                    "pre_anchor_beats": str(seg.get("pre_anchor_beats") or ""),
                    "anchor_frame_state": str(seg.get("anchor_frame_state") or ""),
                    "post_anchor_beats": str(seg.get("post_anchor_beats") or ""),
                    "gap_path_summary": str(seg.get("gap_path_summary") or ""),
                    "api_payload_preview": payload_preview,
                }
            )
        return {
            "dream_text_excerpt": dream_excerpt,
            "lines": [
                {
                    "line_index": 0,
                    "frame_indices": [int(s.get("from_frame_index") or 0) for s in segs],
                    "segments": segs,
                    "note": "single-anchor segments (один сегмент на keyframe)",
                }
            ],
            "line_boundaries": [],
            "n_frames": len(rows),
        }

    # Seedance/keyframe-gap режим: один сегмент между соседними keyframes.
    if len(keyframes) >= 2:
        segs: list[dict[str, Any]] = []
        for j in range(len(keyframes) - 1):
            fi = int(keyframes[j])
            ti = int(keyframes[j + 1])
            f0 = by_idx.get(fi, {})
            f1 = by_idx.get(ti, {})
            tr = tr_by_pair.get((fi, ti), {})
            mode_raw = str(tr.get("segment_mode") or "pairwise").strip().lower().replace("-", "_")
            seg_mode = mode_raw if mode_raw in {"pairwise", "single_anchor"} else "pairwise"
            u0 = lite_first_frame_stored_image_url(f0)
            u1 = lite_first_frame_stored_image_url(f1)
            motion, motion_src = lite_motion_prompt_for_prev_segment(
                dream_text=dream_text or "",
                f0=f0,
                f1=f1,
                transition_plan=transition_plan,
                from_index=fi,
                to_index=ti,
            )
            seg_story = str(tr.get("segment_story") or "").strip()
            bridge = _lite_bridge_text_for_gap(fi, ti, by_idx)
            dialog_hint = _lite_dialog_hint_for_gap(fi, ti, by_idx)
            if bridge:
                motion = f"{motion}\n\n{bridge}"
            if dialog_hint:
                motion = f"{motion}\n\n{dialog_hint}"
            if not seg_story and bridge:
                seg_story = bridge
            motion, seg_story, phase_present, micro_applied = _lite_enforce_phase_microact_contract(
                motion,
                seg_story,
            )
            motion = _lite_clean_motion_prompt_text(motion)
            seg_duration = _lite_normalize_duration_sec(
                tr.get("duration_sec"),
                default_sec=_LITE_DURATION_DEFAULT_SEC,
            )
            final_prompt = _lite_build_unified_i2v_prompt(
                dream_text=dream_text,
                image_prompt=str(f0.get("img_prompt") or "").strip(),
                motion_prompt=motion,
                target_keyframe=ti,
            )
            voiceover = str(tr.get("voiceover_text") or "").strip()
            needs_last = pm == "first_last_frame"
            needs_first = pm != "text_only"
            if needs_last:
                both_ok = bool(u0) if seg_mode == "single_anchor" else bool(u0 and u1)
            else:
                both_ok = bool(u0) if needs_first else True
            segs.append(
                {
                    "segment_index": j,
                    "from_frame_index": fi,
                    "to_frame_index": ti if needs_last else fi,
                    "target_frame_index": ti,
                    "from_title": str(f0.get("title") or f"Кадр {fi + 1}").strip(),
                    "to_title": str(f1.get("title") or f"Кадр {ti + 1}").strip(),
                    "image_url_start": u0 if needs_first else "",
                    "image_url_end": u1 if needs_last else "",
                    "both_images_ready": both_ok,
                    "in_montage_plan": (fi, ti) in edge_set,
                    "montage_mode": mm,
                    "montage_preset": str(montage_preset or "default").strip().lower() or "default",
                    "prompt_mode": pm,
                    "effective_prompt_mode": pm,
                    "effective_prompt_policy": pm_policy,
                    "prompt_mode_locked": bool(pm_locked),
                    "segment_mode": seg_mode,
                    "duration_sec": seg_duration,
                    "segment_story": seg_story,
                    "voiceover_text": voiceover,
                    "phase_timing_text_present": bool(phase_present),
                    "micro_act_contract_applied": bool(tr.get("micro_act_contract_applied") or micro_applied),
                    "motion_prompt_preview": _lite_transition_trim(motion, 260),
                    "motion_prompt_suggested": motion,
                    "final_prompt": final_prompt,
                    "motion_prompt_source": motion_src,
                    "api_payload_preview": (
                        {
                            "reference_image_url": u0,
                            "input_references": [{"type": "image_url", "image_url": u0}] if u0 else [],
                            "prompt": final_prompt,
                            "prompt_mode": "first_frame_only",
                            "effective_prompt_mode": "first_frame_only",
                            "effective_prompt_policy": "locked_kling_reference_motion",
                            "duration_sec": 5,
                            "size": "720x720",
                            "voiceover_text": voiceover,
                        }
                        if kling_ref_mode
                        else {
                            "image_url": u0 if needs_first else "",
                            "last_frame_url": u1 if needs_last else "",
                            "prompt": final_prompt,
                            "motion_prompt": motion,
                            "prompt_mode": pm,
                            "effective_prompt_mode": pm,
                            "effective_prompt_policy": pm_policy,
                            "duration_sec": seg_duration,
                            "voiceover_text": voiceover,
                        }
                    ),
                }
            )
        return {
            "dream_text_excerpt": dream_excerpt,
            "lines": [
                {
                    "line_index": 0,
                    "frame_indices": keyframes,
                    "segments": segs,
                    "note": "keyframe-gap segments",
                }
            ],
            "line_boundaries": [],
            "n_frames": len(rows),
        }

    lines: list[list[int]] = []
    current: list[int] = []
    for f in rows:
        ix = int(f["index"])
        u_prev = bool(f.get("use_previous_frame_resolved"))
        if not current:
            current = [ix]
            continue
        prev_ix = current[-1]
        if ix == prev_ix + 1 and u_prev:
            current.append(ix)
        else:
            lines.append(current)
            current = [ix]
    if current:
        lines.append(current)

    line_payloads: list[dict[str, Any]] = []
    boundaries: list[dict[str, Any]] = []

    for li, line in enumerate(lines):
        segs: list[dict[str, Any]] = []
        if len(line) < 2:
            line_payloads.append(
                {
                    "line_index": li,
                    "frame_indices": line,
                    "segments": [],
                    "note": "Один кадр в линии — нет соседней пары для перехода внутри prev-цепочки.",
                }
            )
            continue
        for j in range(len(line) - 1):
            fi, ti = line[j], line[j + 1]
            f0 = by_idx.get(fi, {})
            f1 = by_idx.get(ti, {})
            seg_mode = "pairwise"
            for tr in list((transition_plan or {}).get("transitions") or []):
                if not isinstance(tr, dict):
                    continue
                try:
                    tr_fi = int(tr.get("from_frame_index"))
                    tr_ti = int(tr.get("to_frame_index"))
                except (TypeError, ValueError):
                    continue
                if tr_fi == fi and tr_ti == ti:
                    mode_raw = str(tr.get("segment_mode") or "pairwise").strip().lower().replace("-", "_")
                    seg_mode = mode_raw if mode_raw in {"pairwise", "single_anchor"} else "pairwise"
                    break
            u0 = lite_first_frame_stored_image_url(f0)
            u1 = lite_first_frame_stored_image_url(f1)
            motion, motion_src = lite_motion_prompt_for_prev_segment(
                dream_text=dream_text or "",
                f0=f0,
                f1=f1,
                transition_plan=transition_plan,
                from_index=fi,
                to_index=ti,
            )
            needs_last = pm == "first_last_frame"
            needs_first = pm != "text_only"
            in_plan = (fi, ti) in edge_set
            final_prompt = _lite_build_unified_i2v_prompt(
                dream_text=dream_text,
                image_prompt=str(f0.get("img_prompt") or "").strip(),
                motion_prompt=motion,
                target_keyframe=ti,
            )
            if needs_last:
                both_ok = bool(u0) if seg_mode == "single_anchor" else bool(u0 and u1)
            else:
                both_ok = bool(u0) if needs_first else True
            segs.append(
                {
                    "segment_index": j,
                    "from_frame_index": fi,
                    "to_frame_index": ti if needs_last else fi,
                    "target_frame_index": ti,
                    "from_title": str(f0.get("title") or f"Кадр {fi + 1}").strip(),
                    "to_title": str(f1.get("title") or f"Кадр {ti + 1}").strip(),
                    "image_url_start": u0 if needs_first else "",
                    "image_url_end": u1 if needs_last else "",
                    "both_images_ready": both_ok,
                    "in_montage_plan": in_plan,
                    "montage_mode": mm,
                    "montage_preset": str(montage_preset or "default").strip().lower() or "default",
                    "prompt_mode": pm,
                    "effective_prompt_mode": pm,
                    "effective_prompt_policy": pm_policy,
                    "prompt_mode_locked": bool(pm_locked),
                    "segment_mode": seg_mode,
                    "motion_prompt_preview": _lite_transition_trim(motion, 260),
                    "motion_prompt_suggested": motion,
                    "final_prompt": final_prompt,
                    "motion_prompt_source": motion_src,
                    "api_payload_preview": (
                        {
                            "reference_image_url": u0,
                            "input_references": [{"type": "image_url", "image_url": u0}] if u0 else [],
                            "prompt": final_prompt,
                            "prompt_mode": "first_frame_only",
                            "effective_prompt_mode": "first_frame_only",
                            "effective_prompt_policy": "locked_kling_reference_motion",
                            "duration_sec": 5,
                            "size": "720x720",
                        }
                        if kling_ref_mode
                        else {
                            "image_url": u0 if needs_first else "",
                            "last_frame_url": u1 if needs_last else "",
                            "prompt": final_prompt,
                            "motion_prompt": motion,
                            "prompt_mode": pm,
                            "effective_prompt_mode": pm,
                            "effective_prompt_policy": pm_policy,
                        }
                    ),
                }
            )
        line_payloads.append(
            {
                "line_index": li,
                "frame_indices": line,
                "segments": segs,
                "note": "",
            }
        )

    for li in range(1, len(lines)):
        left = lines[li - 1]
        right = lines[li]
        boundaries.append(
            {
                "after_frame_index": left[-1],
                "before_frame_index": right[0],
                "message": (
                    f"Новая линия начинается с кадра {right[0]}: следующий кадр не продолжает предыдущий "
                    "(нет prev в image API). Пару «конец кадра {left[-1]} → начало кадра {right[0]}» "
                    "для непрерывного i2v не строим."
                ),
            }
        )

    return {
        "dream_text_excerpt": dream_excerpt,
        "lines": line_payloads,
        "line_boundaries": boundaries,
        "n_frames": len(rows),
    }


def lite_transitions_user_message(
    *,
    dream_text: str,
    env_cards: list[dict[str, Any]],
    char_cards: list[dict[str, Any]],
    generated_frames: list[dict[str, Any]],
    montage_preset: str = "default",
) -> str:
    payload = lite_transitions_user_payload_dict(
        dream_text=dream_text,
        env_cards=env_cards,
        char_cards=char_cards,
        generated_frames=generated_frames,
        montage_preset=montage_preset,
    )
    return (
        "Данные для плана переходов (JSON). "
        "Используй только человеко-понятные описания кадров и динамику действия. "
        "Для keyframe поле image_url дано как визуальный указатель на опорное изображение. "
        "Пиши motion_prompt обычным режиссёрским языком, без технических id и системных терминов. "
        "Верни один JSON-объект по инструкции из system (только JSON, без ``` и без пояснений):\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _extract_json_object_from_text(text: str) -> Any:
    s = (text or "").strip()
    if not s:
        raise ValueError("пустой ответ модели")
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, flags=re.IGNORECASE)
    if m:
        s = (m.group(1) or "").strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        i = s.find("{")
        if i < 0:
            raise ValueError("нет JSON-объекта в ответе") from None
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(s[i:])
        return obj


def _lite_scenes_from_transitions(
    n_frames: int,
    transitions_by_from: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    if n_frames <= 0:
        return []
    if n_frames == 1:
        return [{"scene_index": 0, "from_frame_index": 0, "to_frame_index": 0}]
    scenes: list[dict[str, Any]] = []
    start = 0
    scene_idx = 0
    for i in range(n_frames - 1):
        t = transitions_by_from.get(i) or {
            "from_frame_index": i,
            "to_frame_index": i + 1,
            "transition_type": "hard_cut",
            "cut_reason": "нет строки перехода, разрез",
        }
        if str(t.get("transition_type") or "").strip() == "hard_cut":
            scenes.append(
                {
                    "scene_index": scene_idx,
                    "from_frame_index": start,
                    "to_frame_index": i,
                }
            )
            scene_idx += 1
            start = i + 1
    scenes.append(
        {
            "scene_index": scene_idx,
            "from_frame_index": start,
            "to_frame_index": n_frames - 1,
        }
    )
    return scenes


def _lite_scenes_from_sparse_animates(pairs: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """Одна запись сцены на каждый непрерывный клип animate_transition (from→to)."""
    out: list[dict[str, Any]] = []
    for si, (fi, ti) in enumerate(pairs):
        out.append(
            {
                "scene_index": si,
                "from_frame_index": fi,
                "to_frame_index": ti,
            }
        )
    return out


def _lite_normalize_transition_type(raw_typ: str) -> str:
    typ = str(raw_typ or "").strip()
    if typ in ("animate_transition", "hard_cut"):
        return typ
    low = typ.lower().replace(" ", "_")
    if low in ("animate", "animation", "i2v"):
        return "animate_transition"
    if low in ("cut", "hardcut"):
        return "hard_cut"
    return "hard_cut"


def _lite_keyframes_from_transitions(transitions: list[dict[str, Any]], n_frames: int) -> list[int]:
    if n_frames <= 0:
        return []
    picked: set[int] = {0, n_frames - 1}
    for t in transitions:
        if not isinstance(t, dict):
            continue
        if str(t.get("transition_type") or "") != "animate_transition":
            continue
        try:
            fi = int(t.get("from_frame_index"))
            ti = int(t.get("to_frame_index"))
        except (TypeError, ValueError):
            continue
        if 0 <= fi < n_frames:
            picked.add(fi)
        if 0 <= ti < n_frames:
            picked.add(ti)
    return sorted(picked)


def _lite_normalize_frame_selection(
    *,
    n_frames: int,
    keyframes: list[int],
    raw_selection: list[dict[str, Any]] | None,
) -> tuple[list[int], list[dict[str, Any]]]:
    if n_frames <= 0:
        return [], []
    kf_set = {int(x) for x in keyframes if isinstance(x, int) and 0 <= int(x) < n_frames}
    kf_set.add(0)
    kf_set.add(n_frames - 1)
    by_idx: dict[int, dict[str, Any]] = {}
    for row in list(raw_selection or []):
        if not isinstance(row, dict):
            continue
        try:
            ix = int(row.get("frame_index"))
        except (TypeError, ValueError):
            continue
        if 0 <= ix < n_frames:
            by_idx[ix] = row

    normalized: list[dict[str, Any]] = []
    for i in range(n_frames):
        src = by_idx.get(i) or {}
        selected = bool(src.get("selected")) or (i in kf_set)
        reason = str(src.get("reason") or "").strip()
        if selected and not reason:
            if i in {0, n_frames - 1}:
                reason = "обязательный опорный кадр (граница цепочки)"
            else:
                reason = "выбран как опорный кадр монтажной цепочки"
        if not selected:
            reason = reason or ""
        normalized.append(
            {
                "frame_index": i,
                "selected": bool(selected),
                "reason": _lite_transition_trim(reason, 320),
            }
        )
    keyframes_out = [int(r["frame_index"]) for r in normalized if bool(r.get("selected"))]
    return keyframes_out, normalized


def _lite_frame_environment_key(row: dict[str, Any], index: int) -> str:
    br = str(row.get("base_reference") or "").strip()
    if br:
        return f"base:{br}"
    op = _norm_key(str(row.get("opora") or ""))
    if op:
        return f"op:{op[:48]}"
    return f"frame:{int(index)}"


def _lite_apply_environment_coverage_rules(
    *,
    n_frames: int,
    generated_frames: list[dict[str, Any]],
    keyframes: list[int],
    frame_selection: list[dict[str, Any]],
) -> tuple[list[int], list[dict[str, Any]]]:
    if n_frames <= 0:
        return keyframes, frame_selection
    by_idx_sel: dict[int, dict[str, Any]] = {}
    for row in frame_selection:
        if not isinstance(row, dict):
            continue
        try:
            ix = int(row.get("frame_index"))
        except (TypeError, ValueError):
            continue
        if 0 <= ix < n_frames:
            by_idx_sel[ix] = row
    for i in range(n_frames):
        if i not in by_idx_sel:
            by_idx_sel[i] = {"frame_index": i, "selected": i in keyframes, "reason": ""}

    env_groups: dict[str, list[int]] = {}
    env_keys: list[str] = []
    for i in range(n_frames):
        row = generated_frames[i] if i < len(generated_frames) and isinstance(generated_frames[i], dict) else {}
        key = _lite_frame_environment_key(row, i)
        env_keys.append(key)
        env_groups.setdefault(key, []).append(i)

    selected_set = {int(x) for x in keyframes if isinstance(x, int) and 0 <= int(x) < n_frames}

    # Смена окружения/композиционной базы — критическая граница, оставляем обе стороны переключения.
    for i in range(1, n_frames):
        if env_keys[i] != env_keys[i - 1]:
            for ix in (i - 1, i):
                if ix not in selected_set:
                    selected_set.add(ix)
                    by_idx_sel[ix]["selected"] = True
                    by_idx_sel[ix]["reason"] = "критический переход между окружениями"

    # Adaptive by count:
    # 1-2 кадра в окружении — не резать; >=3 — минимум 2 кадра.
    for _, idxs in env_groups.items():
        if not idxs:
            continue
        count = len(idxs)
        min_keep = count if count <= 2 else 2
        picked = [ix for ix in idxs if ix in selected_set]
        if len(picked) < min_keep:
            preferred = [idxs[0], idxs[-1]]
            for ix in preferred:
                if ix in selected_set:
                    continue
                selected_set.add(ix)
                by_idx_sel[ix]["selected"] = True
                by_idx_sel[ix]["reason"] = "покрытие окружения (adaptive_by_count)"
                picked.append(ix)
                if len(picked) >= min_keep:
                    break

    # Если модель выбрала "всё подряд" и кадров много, компактим выбор внутри длинных окружений.
    if len(selected_set) == n_frames and n_frames >= 4:
        for _, idxs in env_groups.items():
            if len(idxs) < 3:
                continue
            keep = {idxs[0], idxs[-1]}
            for ix in idxs:
                if ix in keep:
                    continue
                if ix in selected_set:
                    selected_set.remove(ix)
                    by_idx_sel[ix]["selected"] = False
                    by_idx_sel[ix]["reason"] = "компактизация длинной серии в окружении"

    selected_sorted = sorted(selected_set)
    normalized_out: list[dict[str, Any]] = []
    for i in range(n_frames):
        row = by_idx_sel[i]
        if row.get("selected") and not str(row.get("reason") or "").strip():
            row["reason"] = "выбран как опорный кадр монтажной цепочки"
        normalized_out.append(
            {
                "frame_index": i,
                "selected": bool(row.get("selected")),
                "reason": _lite_transition_trim(str(row.get("reason") or "").strip(), 320),
            }
        )
    return selected_sorted, normalized_out


def _lite_sparse_transitions_from_keyframes(
    *,
    keyframes: list[int],
    plan_transitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(keyframes) < 2:
        return []
    by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    for t in plan_transitions:
        if not isinstance(t, dict):
            continue
        if str(t.get("transition_type") or "") != "animate_transition":
            continue
        try:
            fi = int(t.get("from_frame_index"))
            ti = int(t.get("to_frame_index"))
        except (TypeError, ValueError):
            continue
        by_pair[(fi, ti)] = dict(t)
    out: list[dict[str, Any]] = []
    for i in range(len(keyframes) - 1):
        fi = int(keyframes[i])
        ti = int(keyframes[i + 1])
        src = by_pair.get((fi, ti))
        if src:
            out.append(src)
            continue
        motion_fb, story_fb, phase_fb, micro_fb = _lite_enforce_phase_microact_contract(
            "Плавный переход между опорными кадрами, без смены художественного стиля.",
            "Плавно довести действие от текущего keyframe к следующему.",
        )
        out.append(
            {
                "from_frame_index": fi,
                "to_frame_index": ti,
                "transition_type": "animate_transition",
                "motion_prompt": motion_fb,
                "segment_mode": "pairwise",
                "duration_sec": 7,
                "segment_story": story_fb,
                "phase_timing_text_present": bool(phase_fb),
                "micro_act_contract_applied": bool(micro_fb),
            }
        )
    return out


def lite_transition_plan_with_selection(
    transition_plan: dict[str, Any] | None,
    n_frames: int,
    *,
    source_hint: str = "",
    generated_frames: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    plan = dict(transition_plan or {})
    if n_frames <= 0:
        plan["keyframes"] = []
        plan["frame_selection"] = []
        plan["frame_selection_source"] = source_hint or "empty"
        return plan

    transitions = [dict(x) for x in list(plan.get("transitions") or []) if isinstance(x, dict)]
    raw_keyframes: list[int] = []
    if isinstance(plan.get("keyframes"), list):
        for x in list(plan.get("keyframes") or []):
            try:
                ix = int(x)
            except (TypeError, ValueError):
                continue
            if 0 <= ix < n_frames:
                raw_keyframes.append(ix)
    if not raw_keyframes:
        raw_keyframes = _lite_keyframes_from_transitions(transitions, n_frames)
    raw_selection = [dict(x) for x in list(plan.get("frame_selection") or []) if isinstance(x, dict)]
    keyframes_out, selection_out = _lite_normalize_frame_selection(
        n_frames=n_frames,
        keyframes=sorted(set(raw_keyframes)),
        raw_selection=raw_selection,
    )
    if generated_frames:
        keyframes_out, selection_out = _lite_apply_environment_coverage_rules(
            n_frames=n_frames,
            generated_frames=list(generated_frames),
            keyframes=keyframes_out,
            frame_selection=selection_out,
        )

    transitions_compacted = _lite_sparse_transitions_from_keyframes(
        keyframes=keyframes_out,
        plan_transitions=transitions,
    )
    if transitions_compacted and (
        str(plan.get("montage_mode") or "").strip().lower() in {"dense", "dense_fallback"}
        or len(keyframes_out) < n_frames
    ):
        plan["transitions"] = transitions_compacted
        plan["scenes"] = _lite_scenes_from_sparse_animates(
            [(int(t["from_frame_index"]), int(t["to_frame_index"])) for t in transitions_compacted]
        )
        plan["montage_mode"] = "sparse"
        plan["selection_compacted"] = True
    if not source_hint:
        if raw_selection:
            source_hint = "model_frame_selection"
        elif isinstance(plan.get("keyframes"), list) and bool(plan.get("keyframes")):
            source_hint = "model_keyframes"
        else:
            source_hint = "derived_from_transitions"
    plan["keyframes"] = keyframes_out
    plan["frame_selection"] = selection_out
    plan["frame_selection_source"] = source_hint
    return plan


def _lite_coerce_transition_row(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    try:
        f = int(item.get("from_frame_index"))
        t = int(item.get("to_frame_index"))
    except (TypeError, ValueError):
        return None
    typ = _lite_normalize_transition_type(str(item.get("transition_type") or ""))
    row: dict[str, Any] = {
        "from_frame_index": f,
        "to_frame_index": t,
        "transition_type": typ,
    }
    if typ == "animate_transition":
        mp = str(item.get("motion_prompt") or "").strip()
        if not mp:
            mp = "изменение позы и кадра между ключами"
        sm = str(item.get("segment_mode") or "").strip().lower().replace("-", "_")
        if sm not in {"pairwise", "single_anchor"}:
            sm = "pairwise"
        row["segment_mode"] = sm
        story = item.get("story_critical")
        if story is not None:
            row["story_critical"] = bool(story)
        duration_sec = _lite_normalize_duration_sec(
            item.get("duration_sec"),
            default_sec=_LITE_DURATION_DEFAULT_SEC,
        )
        row["duration_sec"] = duration_sec
        seg_story = str(item.get("segment_story") or "").strip()
        voiceover = str(item.get("voiceover_text") or "").strip()
        seedance_contract_hint = bool(duration_sec or seg_story or voiceover)
        if seedance_contract_hint:
            mp, seg_story, phase_present, micro_act_applied = _lite_enforce_phase_microact_contract(mp, seg_story)
            row["phase_timing_text_present"] = bool(phase_present)
            row["micro_act_contract_applied"] = bool(micro_act_applied)
        row["motion_prompt"] = _lite_transition_trim(mp, 800)
        if seg_story:
            row["segment_story"] = _lite_transition_trim(seg_story, 400)
        voiceover = str(item.get("voiceover_text") or "").strip()
        if voiceover:
            row["voiceover_text"] = _lite_transition_trim(voiceover, 400)
        anchor_role = str(item.get("anchor_role") or "").strip().lower()
        if anchor_role in {"scene_start", "central_moment"}:
            row["anchor_role"] = anchor_role
        if item.get("is_scene_start") is not None:
            row["is_scene_start"] = bool(item.get("is_scene_start"))
        pre_anchor_beats = str(item.get("pre_anchor_beats") or "").strip()
        if pre_anchor_beats:
            row["pre_anchor_beats"] = _lite_transition_trim(pre_anchor_beats, 300)
        anchor_frame_state = str(item.get("anchor_frame_state") or "").strip()
        if anchor_frame_state:
            row["anchor_frame_state"] = _lite_transition_trim(anchor_frame_state, 300)
        post_anchor_beats = str(item.get("post_anchor_beats") or "").strip()
        if post_anchor_beats:
            row["post_anchor_beats"] = _lite_transition_trim(post_anchor_beats, 300)
    else:
        cr = str(item.get("cut_reason") or "").strip()
        if not cr:
            cr = "монтажный разрез"
        row["cut_reason"] = cr
    return row


def _lite_is_dense_legacy_transitions(trans_in: list[Any], n_frames: int) -> bool:
    if n_frames <= 1 or len(trans_in) != n_frames - 1:
        return False
    for i, item in enumerate(trans_in):
        if not isinstance(item, dict):
            return False
        try:
            f = int(item.get("from_frame_index"))
            t = int(item.get("to_frame_index"))
        except (TypeError, ValueError):
            return False
        if f != i or t != i + 1:
            return False
    return True


def _lite_validate_sparse_animate_chain(
    pairs: list[tuple[int, int]],
    n_frames: int,
) -> None:
    if not pairs:
        raise ValueError("нет animate_transition в разрежённом плане")
    pairs = sorted(pairs, key=lambda x: x[0])
    if pairs[0][0] != 0:
        raise ValueError("цепочка animate должна начинаться с кадра 0")
    if pairs[-1][1] != n_frames - 1:
        raise ValueError("цепочка animate должна заканчиваться на последнем кадре")
    for i, (f, t) in enumerate(pairs):
        if f < 0 or t >= n_frames or f >= t:
            raise ValueError("некорректные индексы в animate_transition")
        if i > 0 and pairs[i - 1][1] != f:
            raise ValueError("разрыв в цепочке animate: стыкуйте to предыдущей пары с from следующей")


def lite_default_transition_plan(n_frames: int) -> dict[str, Any]:
    if n_frames <= 0:
        return {"scenes": [], "transitions": [], "montage_mode": "hard_cut_fallback"}
    if n_frames == 1:
        return {
            "scenes": [{"scene_index": 0, "from_frame_index": 0, "to_frame_index": 0}],
            "transitions": [],
            "montage_mode": "hard_cut_fallback",
        }
    transitions: list[dict[str, Any]] = []
    for i in range(n_frames - 1):
        transitions.append(
            {
                "from_frame_index": i,
                "to_frame_index": i + 1,
                "transition_type": "hard_cut",
                "cut_reason": "дефолт: разрез (ошибка разбора плана)",
            }
        )
    by_from = {t["from_frame_index"]: t for t in transitions}
    return {
        "scenes": _lite_scenes_from_transitions(n_frames, by_from),
        "transitions": transitions,
        "montage_mode": "hard_cut_fallback",
    }


def lite_dense_animate_fallback_plan(n_frames: int) -> dict[str, Any]:
    """
    Все соседние пары — animate_transition (безопасный дефолт при ошибке LLM / парсера).
    Даёт непрерывную цепочку i2v вместо all-hard_cut, у которой нет клипов.
    """
    if n_frames <= 0:
        return {"scenes": [], "transitions": [], "montage_mode": "dense_fallback"}
    if n_frames == 1:
        return {
            "scenes": [{"scene_index": 0, "from_frame_index": 0, "to_frame_index": 0}],
            "transitions": [],
            "montage_mode": "dense_fallback",
        }
    transitions: list[dict[str, Any]] = []
    for i in range(n_frames - 1):
        transitions.append(
            {
                "from_frame_index": i,
                "to_frame_index": i + 1,
                "transition_type": "animate_transition",
                "motion_prompt": "Плавное движение камеры и фигур между ключами, та же сцена.",
                "segment_mode": "pairwise",
            }
        )
    by_from = {t["from_frame_index"]: t for t in transitions}
    return {
        "scenes": _lite_scenes_from_transitions(n_frames, by_from),
        "transitions": transitions,
        "montage_mode": "dense_fallback",
    }


def lite_plan_animate_edge_set(transition_plan: dict[str, Any] | None) -> set[tuple[int, int]]:
    """Пары (from,to) с animate_transition — для UI и prev-line."""
    out: set[tuple[int, int]] = set()
    plan = transition_plan or {}
    for t in plan.get("transitions") or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("transition_type") or "") != "animate_transition":
            continue
        try:
            out.add((int(t.get("from_frame_index")), int(t.get("to_frame_index"))))
        except (TypeError, ValueError):
            continue
    return out


def _parse_lite_transition_plan_from_model_text_impl(raw: str, n_frames: int) -> dict[str, Any]:
    """
    Разбор JSON: плотный legacy (N−1 соседних рёбер) или разрежённый (цепочка from→to).
    При ошибке — ValueError.
    """
    if n_frames <= 0:
        return lite_default_transition_plan(0)
    if n_frames == 1:
        return lite_default_transition_plan(1)

    data = _extract_json_object_from_text(raw)
    if not isinstance(data, dict):
        raise ValueError("корень ответа должен быть объектом")
    frame_selection_model = [
        dict(x)
        for x in list(data.get("frame_selection") or [])
        if isinstance(x, dict)
    ]

    trans_in = data.get("transitions")
    if not isinstance(trans_in, list):
        raise ValueError("transitions должен быть массивом")

    extra: dict[str, Any] = {}
    msi = data.get("must_animate_frame_indices")
    if isinstance(msi, list):
        try:
            extra["must_animate_frame_indices"] = [int(x) for x in msi]
        except (TypeError, ValueError):
            pass
    msi2 = data.get("story_critical_frame_indices")
    if isinstance(msi2, list):
        try:
            extra["story_critical_frame_indices"] = [int(x) for x in msi2]
        except (TypeError, ValueError):
            pass

    coerced: list[dict[str, Any]] = []
    for item in trans_in:
        row = _lite_coerce_transition_row(item if isinstance(item, dict) else {})
        if row:
            coerced.append(row)

    # --- Явные keyframes: строим цепочку пар ---
    kf_raw = data.get("keyframes")
    if isinstance(kf_raw, list) and kf_raw:
        kf_set: set[int] = set()
        for x in kf_raw:
            try:
                kf_set.add(int(x))
            except (TypeError, ValueError):
                continue
        kf_set.add(0)
        kf_set.add(n_frames - 1)
        kf_sorted = sorted(kf_set)
        for a, b in zip(kf_sorted, kf_sorted[1:]):
            if a >= b:
                raise ValueError("keyframes должны быть строго возрастающими после нормализации")
        pairs_kf = [(kf_sorted[i], kf_sorted[i + 1]) for i in range(len(kf_sorted) - 1)]
        _lite_validate_sparse_animate_chain(pairs_kf, n_frames)

        motion_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
        for row in coerced:
            if row.get("transition_type") == "animate_transition":
                motion_by_pair[(int(row["from_frame_index"]), int(row["to_frame_index"]))] = row

        transitions_out: list[dict[str, Any]] = []
        for fi, ti in pairs_kf:
            src = motion_by_pair.get((fi, ti))
            if src:
                transitions_out.append(dict(src))
            else:
                mp_fb, story_fb, phase_fb, micro_fb = _lite_enforce_phase_microact_contract(
                    "Плавное движение между ключами; развитие сцены по текстам кадров.",
                    "",
                )
                transitions_out.append(
                    {
                        "from_frame_index": fi,
                        "to_frame_index": ti,
                        "transition_type": "animate_transition",
                        "motion_prompt": mp_fb,
                        "segment_mode": "pairwise",
                        "duration_sec": 7,
                        "segment_story": story_fb,
                        "phase_timing_text_present": bool(phase_fb),
                        "micro_act_contract_applied": bool(micro_fb),
                    }
                )

        scenes_model = data.get("scenes")
        scenes: list[dict[str, Any]]
        if isinstance(scenes_model, list) and scenes_model:
            scenes = []
            for i, s in enumerate(scenes_model):
                if not isinstance(s, dict):
                    continue
                try:
                    scenes.append(
                        {
                            "scene_index": int(s.get("scene_index", i)),
                            "from_frame_index": int(s.get("from_frame_index")),
                            "to_frame_index": int(s.get("to_frame_index")),
                            **({"scene_summary": str(s.get("scene_summary") or "").strip()} if s.get("scene_summary") else {}),
                        }
                    )
                except (TypeError, ValueError):
                    continue
            if not scenes:
                scenes = _lite_scenes_from_sparse_animates(pairs_kf)
        else:
            scenes = _lite_scenes_from_sparse_animates(pairs_kf)

        out = {
            "scenes": scenes,
            "transitions": transitions_out,
            "montage_mode": "sparse",
            "keyframes": list(kf_sorted),
            **extra,
        }
        if frame_selection_model:
            out["frame_selection"] = frame_selection_model
        return out

    # --- Плотный legacy: ровно N−1 соседних рёбер ---
    if _lite_is_dense_legacy_transitions(trans_in, n_frames):
        by_from: dict[int, dict[str, Any]] = {}
        for item in trans_in:
            if not isinstance(item, dict):
                continue
            row = _lite_coerce_transition_row(item)
            if not row:
                continue
            by_from[int(row["from_frame_index"])] = row

        transitions: list[dict[str, Any]] = []
        for i in range(n_frames - 1):
            t = by_from.get(i)
            if (
                not t
                or int(t.get("to_frame_index", -1)) != i + 1
                or int(t.get("from_frame_index", -2)) != i
            ):
                t = {
                    "from_frame_index": i,
                    "to_frame_index": i + 1,
                    "transition_type": "hard_cut",
                    "cut_reason": "некорректная пара индексов у модели",
                }
            transitions.append(t)

        scenes = _lite_scenes_from_transitions(n_frames, {x["from_frame_index"]: x for x in transitions})
        out = {"scenes": scenes, "transitions": transitions, "montage_mode": "dense", **extra}
        if frame_selection_model:
            out["frame_selection"] = frame_selection_model
        return out

    # --- Разрежённый: только цепочка animate ---
    dedup_animate: dict[tuple[int, int], dict[str, Any]] = {}
    for r in coerced:
        if r.get("transition_type") != "animate_transition":
            continue
        k = (int(r["from_frame_index"]), int(r["to_frame_index"]))
        dedup_animate[k] = r
    pairs_sorted = sorted(dedup_animate.keys(), key=lambda x: x[0])
    _lite_validate_sparse_animate_chain(pairs_sorted, n_frames)
    animates = [dedup_animate[k] for k in pairs_sorted]

    scenes_model = data.get("scenes")
    if isinstance(scenes_model, list) and scenes_model:
        scenes_sparse: list[dict[str, Any]] = []
        for i, s in enumerate(scenes_model):
            if not isinstance(s, dict):
                continue
            try:
                scenes_sparse.append(
                    {
                        "scene_index": int(s.get("scene_index", i)),
                        "from_frame_index": int(s.get("from_frame_index")),
                        "to_frame_index": int(s.get("to_frame_index")),
                        **({"scene_summary": str(s.get("scene_summary") or "").strip()} if s.get("scene_summary") else {}),
                    }
                )
            except (TypeError, ValueError):
                continue
        scenes = scenes_sparse if scenes_sparse else _lite_scenes_from_sparse_animates(pairs_sorted)
    else:
        scenes = _lite_scenes_from_sparse_animates(pairs_sorted)

    out = {
        "scenes": scenes,
        "transitions": animates,
        "montage_mode": "sparse",
        **extra,
    }
    if frame_selection_model:
        out["frame_selection"] = frame_selection_model
    return out


def parse_lite_transition_plan_from_model_text(
    raw: str,
    n_frames: int,
    *,
    fallback_on_error: bool = True,
) -> dict[str, Any]:
    """
    Разбор и нормализация JSON от модели.
    Плотный режим: N−1 рёбер между соседями; разрежённый: цепочка animate с возможными пропусками индексов.
    При fallback_on_error=True ошибка парсинга даёт lite_dense_animate_fallback_plan (на i2v есть клипы).
    """
    try:
        parsed = _parse_lite_transition_plan_from_model_text_impl(raw, n_frames)
        source_hint = (
            "model_frame_selection"
            if bool(parsed.get("frame_selection"))
            else (
                "model_keyframes"
                if isinstance(parsed.get("keyframes"), list) and bool(parsed.get("keyframes"))
                else ""
            )
        )
        return lite_transition_plan_with_selection(parsed, n_frames, source_hint=source_hint)
    except (ValueError, json.JSONDecodeError):
        if not fallback_on_error:
            raise
        plan = lite_dense_animate_fallback_plan(n_frames)
        plan["_parse_fallback"] = True
        return lite_transition_plan_with_selection(
            plan,
            n_frames,
            source_hint="fallback_from_dense_transitions",
        )


async def lite_compute_transition_plan(
    openai: Any,
    *,
    dream_text: str,
    env_cards: list[dict[str, Any]],
    char_cards: list[dict[str, Any]],
    generated_frames: list[dict[str, Any]],
    transition_system_prompt: str | None = None,
    montage_preset: str = "default",
) -> dict[str, Any]:
    """Один вызов чата + разбор JSON; при 0–1 кадре без вызова модели."""
    frames_with_index: list[dict[str, Any]] = []
    for i, row in enumerate(generated_frames):
        if not isinstance(row, dict):
            continue
        d = dict(row)
        if "index" not in d:
            d["index"] = i
        frames_with_index.append(d)
    n = len(frames_with_index)
    if n <= 1:
        return lite_default_transition_plan(n)

    user = lite_transitions_user_message(
        dream_text=dream_text,
        env_cards=env_cards,
        char_cards=char_cards,
        generated_frames=frames_with_index,
        montage_preset=montage_preset,
    )
    raw = await lite_chat_text(
        openai,
        system=(transition_system_prompt or "").strip() or lite_transitions_system_prompt(),
        user=user,
    )
    return parse_lite_transition_plan_from_model_text(raw, n)


def split_markdown_h3_sections(text: str) -> list[dict[str, Any]]:
    """
    Делит текст по заголовкам ### (первая строка заголовка — title, остальное — body).
    Если заголовков нет — один блок целиком.
    """
    raw = (text or "").strip()
    if not raw:
        return []

    parts = re.split(r"^###\s+", raw, flags=re.MULTILINE)
    out: list[dict[str, Any]] = []

    if parts[0].strip():
        out.append({"title": "Ввод", "body": parts[0].strip(), "is_preamble": True})

    for p in parts[1:]:
        chunk = p.strip()
        if not chunk:
            continue
        lines = chunk.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        out.append({"title": title, "body": body, "is_preamble": False})

    if not out and raw:
        return [{"title": "Результат", "body": raw, "is_preamble": False}]

    if len(out) == 1 and out[0].get("is_preamble"):
        return [{"title": "Окружения", "body": out[0]["body"], "is_preamble": False}]

    return [b for b in out if not b.get("is_preamble")] or [
        {"title": "Результат", "body": raw, "is_preamble": False}
    ]


def split_h3_cards_in_block(block: str) -> list[dict[str, Any]]:
    """Карточки `### title` внутри одной секции (тело без ##)."""
    raw = (block or "").strip()
    if not raw:
        return []
    parts = re.split(r"^###\s+", raw, flags=re.MULTILINE)
    out: list[dict[str, Any]] = []
    for p in parts[1:]:
        chunk = p.strip()
        if not chunk:
            continue
        lines = chunk.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if title:
            out.append({"title": title, "body": body})
    if not out and raw:
        return [{"title": "блок", "body": raw}]
    return out


def split_lite_step1_world(raw: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Делит ответ шага 1 на окружения и персонажей по заголовкам ## Окружения / ## Персонажи.
    Без секций — весь текст считается только окружениями (обратная совместимость).
    """
    text = (raw or "").strip()
    if not text:
        return [], []

    e_m = re.search(r"(?im)^##\s*Окружения\s*$", text)
    c_m = re.search(r"(?im)^##\s*Персонажи\s*$", text)

    if not e_m and not c_m:
        return split_markdown_h3_sections(text), []

    if e_m and c_m:
        if e_m.start() < c_m.start():
            env_block = text[e_m.end() : c_m.start()].strip()
            char_block = text[c_m.end() :].strip()
        else:
            char_block = text[c_m.end() : e_m.start()].strip()
            env_block = text[e_m.end() :].strip()
    elif e_m:
        env_block = text[e_m.end() :].strip()
        char_block = ""
    else:
        env_block = ""
        char_block = text[c_m.end() :].strip() if c_m else ""

    env_cards = split_h3_cards_in_block(env_block)
    char_cards = split_h3_cards_in_block(char_block)
    return env_cards, char_cards


def split_lite_frame_cards(text: str) -> list[dict[str, Any]]:
    """Кадры: строки `### Кадр N` / `### Frame N` (допускается `:` в конце), только заголовок на строке."""
    raw = (text or "").strip()
    if not raw:
        return []

    pattern = r"(?im)^###\s*(?:Кадр|Frame)\s*(\d+)\s*[:：]?\s*$"
    matches = list(re.finditer(pattern, raw, flags=re.IGNORECASE))
    if not matches:
        return [b for b in split_markdown_h3_sections(raw) if not b.get("is_preamble", True)]

    out: list[dict[str, Any]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        num = m.group(1)
        body = raw[start:end].strip()
        out.append({"title": f"Кадр {num}", "body": body, "is_preamble": False})

    return out if out else [{"title": "Кадры", "body": raw, "is_preamble": False}]


def _parse_bool_loose(s: str) -> bool | None:
    x = (s or "").strip().lower()
    if x in ("true", "yes", "1", "да", "y", "on"):
        return True
    if x in ("false", "no", "0", "нет", "n", "off"):
        return False
    return None


def _parse_character_references_list(s: str) -> list[str]:
    raw = (s or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        parts = re.split(r"[,|]", inner)
        toks = [p.strip().strip("'\"") for p in parts if p.strip()]
    else:
        parts = re.split(r"[,;|]", raw)
        toks = [p.strip() for p in parts if p.strip()]
    norm = [_normalize_lite_character_id_token(p) for p in toks]
    return _dedupe_str_list([x for x in norm if x])


def parse_frame_body_fields(body: str) -> dict[str, Any]:
    """
    Поля: Опора / Изменение / Кадр / Результат и явные base_reference, character_references,
    use_previous_frame, is_keyframe, keyframe_reason, delta, frame_text.
    """
    text = (body or "").strip()
    out: dict[str, Any] = {
        "opora": "",
        "izmenenie": "",
        "kad": "",
        "base_reference": "",
        "character_references": "",
        "use_previous_frame": "",
        "is_keyframe": "",
        "keyframe_reason": "",
        "delta": "",
        "frame_text": "",
    }
    if not text:
        return out

    pat = re.compile(
        r"(?ims)^\*{0,2}\s*"
        r"(Опора|Изменение|Кадр|Результат|base_reference|character_references|use_previous_frame|is_keyframe|keyframe_reason|delta|frame_text)\s*"
        r"\*{0,2}\s*[:：]\s*"
        r"(.+?)(?=^\*{0,2}\s*"
        r"(?:Опора|Изменение|Кадр|Результат|base_reference|character_references|use_previous_frame|is_keyframe|keyframe_reason|delta|frame_text)\s*"
        r"\*{0,2}\s*[:：]|\Z)",
    )
    found_labeled = False
    for m in pat.finditer(text):
        found_labeled = True
        key = (m.group(1) or "").strip()
        val = ((m.group(2) or "").strip())[:8000]
        if key == "Опора":
            out["opora"] = val
        elif key == "Изменение":
            out["izmenenie"] = val
        elif key in ("Кадр", "Результат"):
            if not out["kad"]:
                out["kad"] = val
        elif key == "base_reference":
            out["base_reference"] = val
        elif key == "character_references":
            out["character_references"] = val
        elif key == "use_previous_frame":
            out["use_previous_frame"] = val
        elif key == "is_keyframe":
            out["is_keyframe"] = val
        elif key == "keyframe_reason":
            out["keyframe_reason"] = val
        elif key == "delta":
            out["delta"] = val
        elif key == "frame_text":
            out["frame_text"] = val
    # Если в карточке уже есть размеченные поля, но «Кадр»/«Результат» пусты — не подставляем
    # весь body в kad: туда попадёт опора, base_reference и т.д. (мусор для image API).
    # Целиком body оставляем только для свободного текста без меток полей.
    if not out["kad"] and not found_labeled:
        out["kad"] = text
    return out


def _strip_md_bold_noise(s: str) -> str:
    """Убирает типичный мусор вроде ведущих `**` из ответа модели."""
    t = (s or "").strip()
    t = re.sub(r"^\*+\s*", "", t)
    t = re.sub(r"\s*\*+$", "", t)
    return t.strip()


def _normalize_lite_character_id_token(raw: str) -> str:
    """
    Один id персонажа из шага 1: модель часто пишет `** [dreamer]**, dreamer` — два слота на одного.
    Убираем markdown-звёздочки, обрамление скобками, кавычки.
    """
    t = (raw or "").strip()
    if not t:
        return ""
    t = t.replace("［", "[").replace("］", "]")
    t = re.sub(r"\*+", "", t)
    t = t.strip()
    if t.startswith("[") and t.endswith("]"):
        t = t[1:-1].strip()
    t = t.strip("`'\"«»")
    return t.strip()


def _canonical_lite_char_id(token: str, known_titles: list[str]) -> str:
    """Один регистр/написание с карточками шага 1: Dreamer и dreamer → как в ### заголовке шага 1."""
    t = _normalize_lite_character_id_token(token)
    if not t:
        return ""
    nk = _norm_key(t)
    for c in known_titles:
        ct = (c or "").strip()
        if not ct:
            continue
        if ct == t or _norm_key(ct) == nk:
            return ct
    return t


def lite_effective_use_previous_frame(
    card: dict[str, Any],
    frame_index: int,
) -> bool:
    """
    Намерение «prev в image API» задаёт **шаг 2b** (классификатор): в карточке поле `use_previous_frame`.
    Поле отсутствует или не распознано → **false** (без догадок в коде).
    """
    if frame_index == 0:
        return False
    v = card.get("use_previous_frame")
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip():
        p = _parse_bool_loose(v)
        if p is not None:
            return p
    return False


def lite_prev_link_streak_from_entries(prior_frame_entries: list[dict[str, Any]]) -> int:
    """Число последних подряд сгенерированных кадров, у которых в генерацию шёл предыдущий кадр."""
    streak = 0
    for e in reversed(prior_frame_entries):
        if not isinstance(e, dict):
            break
        if e.get("use_previous_frame_resolved"):
            streak += 1
        else:
            break
    return streak


def lite_resolve_use_previous_frame(
    card: dict[str, Any],
    frame_index: int,
    *,
    prior_frame_entries: list[dict[str, Any]],
    simple_mode: bool = False,
) -> tuple[bool, bool]:
    """
    Итоговое решение для генерации: (use_previous_resolved, forced_chain_break).
    forced_chain_break оставлен для обратной совместимости поля; в актуальной scene-aware политике
    технический лимит длины prev-цепочки не применяется.
    """
    wants = lite_effective_use_previous_frame(card, frame_index)
    if frame_index == 0:
        card["prev_resolution_reason"] = "first_frame_no_previous"
        card["prev_pair_state"] = "closed"
        return False, False
    if not wants:
        card["prev_resolution_reason"] = "model_or_policy_no_previous"
        card["prev_pair_state"] = "closed"
        return False, False
    if simple_mode:
        streak = lite_prev_link_streak_from_entries(prior_frame_entries)
        if streak >= 1:
            card["prev_resolution_reason"] = "simple_mode_cap2_forced_break_after_pair"
            card["prev_pair_state"] = "closed"
            return False, True
        card["prev_resolution_reason"] = "simple_mode_pair_open"
        card["prev_pair_state"] = "open"
        return True, False
    card["prev_resolution_reason"] = "continuity_requested"
    card["prev_pair_state"] = "open"
    return True, False


def lite_ref_urls_for_ui(urls: list[str]) -> list[str]:
    """Короткие подписи для HTML/логов без многомегабайтных data URI."""
    out: list[str] = []
    for u in urls:
        u = str(u or "").strip()
        if not u:
            continue
        if u.startswith("data:"):
            out.append(f"data:… ({len(u)} симв.)")
        elif len(u) > 96:
            out.append(u[:40] + "…" + u[-24:])
        else:
            out.append(u)
    return out


def _dedupe_str_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        x = (x or "").strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _dedupe_lite_character_ids(items: list[str], known_titles: list[str]) -> list[str]:
    """Один человек — один id в списке (dreamer / Dreamer не дублируются)."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        c = _canonical_lite_char_id(str(x), known_titles)
        if not c:
            continue
        nk = _norm_key(c)
        if nk in seen:
            continue
        seen.add(nk)
        out.append(c)
    return out


def infer_missing_character_references(
    card: dict[str, Any],
    step1_char_titles: list[str],
) -> None:
    """
    Если LLM не выписала character_references, подставить id из шага 1 по тексту кадра
    (в т.ч. «сновидец» → карточка dreamer).
    """
    if list(card.get("character_references") or []):
        return
    titles = [(t or "").strip() for t in step1_char_titles if (t or "").strip()]
    if not titles:
        return
    blob = _norm_key(
        f"{card.get('opora', '')} {card.get('izmenenie', '')} {card.get('kad', '')}"
    )
    if not blob:
        return
    inferred: list[str] = []
    for t in titles:
        nt = _norm_key(t)
        if len(nt) >= 2 and nt in blob:
            inferred.append(t)
            continue
        for w in nt.split():
            if len(w) > 2 and w in blob:
                inferred.append(t)
                break
    dream_hints = (
        "сновидец",
        "сновидица",
        "сновидца",
        "сновидцу",
        "dreamer",
        "дример",
        "дриммер",
    )
    if not inferred and any(h in blob for h in dream_hints):
        for t in titles:
            tl = (t or "").lower()
            if tl == "dreamer" or tl.startswith("dreamer_"):
                inferred.append(t)
                break
            if "dream" in tl:
                inferred.append(t)
                break
    if inferred:
        card["character_references"] = _dedupe_str_list(inferred)
        card["character_references_inferred"] = True
        logger.info(
            "dream_lite шаг 2: автоподстановка character_references %s (текст кадра ↔ id шага 1)",
            inferred,
        )


def ensure_dreamer_in_frame_character_refs(
    card: dict[str, Any],
    step1_char_titles: list[str],
) -> None:
    """
    Главный персонаж (dreamer / protagonist) часто выпадает из character_references на поздних кадрах —
    тогда в цепочке нет его листа. Добавляем id сновидца, если в кадре уже есть другие люди или явные маркеры.
    """
    titles = [(t or "").strip() for t in step1_char_titles if (t or "").strip()]
    if not titles:
        return
    dr: str | None = None
    for t in titles:
        tl = (t or "").lower()
        if tl == "dreamer" or tl.startswith("dreamer_") or tl == "protagonist":
            dr = t
            break
    if dr is None:
        for t in titles:
            if "dream" in _norm_key(t):
                dr = t
                break
    if not dr:
        return
    dr_key = _norm_key(_canonical_lite_char_id(dr, titles))
    keys_present = {
        _norm_key(_canonical_lite_char_id(str(x), titles))
        for x in (card.get("character_references") or [])
        if str(x).strip()
    }
    if dr_key in keys_present:
        return
    refs = [str(x).strip() for x in (card.get("character_references") or []) if str(x).strip()]
    blob = _norm_key(
        f"{card.get('opora', '')} {card.get('izmenenie', '')} {card.get('kad', '')}"
    )
    dream_hints = (
        "сновидец",
        "сновидица",
        "сновидца",
        "сновидцу",
        "dreamer",
        "дример",
    )
    other_ids = [t for t in titles if _norm_key(t) != _norm_key(dr)]
    other_hit = any(_norm_key(t) in blob for t in other_ids)
    dream_hit = any(h in blob for h in dream_hints)
    if refs:
        if other_hit or dream_hit or len(refs) >= 2:
            card["character_references"] = _dedupe_str_list([dr] + refs)
            card["dreamer_ref_injected"] = True
            logger.info("dream_lite шаг 2: в кадр добавлен %s (главный персонаж)", dr)
    elif blob and (dream_hit or other_hit):
        card["character_references"] = [dr]
        card["dreamer_ref_injected"] = True
        logger.info("dream_lite шаг 2: в пустые character_references добавлен %s", dr)


def _append_lite_frame_ui_fields(idx: int, d: dict[str, Any]) -> None:
    """Короткие строки для компактного UI шага 2."""
    chars = list(d.get("character_references") or [])
    auto = bool(d.get("character_references_inferred"))
    carried = bool(d.get("character_references_carried"))
    inj = bool(d.get("dreamer_ref_injected"))
    if chars:
        tags: list[str] = []
        if auto:
            tags.append("авто")
        if carried:
            tags.append("с пред. кадра")
        if inj:
            tags.append("+dreamer")
        suf = (" · " + " · ".join(tags)) if tags else ""
        d["ui_chars_line"] = ", ".join(chars) + suf
    else:
        d["ui_chars_line"] = "—"

    br = str(d.get("base_reference") or "").strip()
    op = _strip_md_bold_noise(str(d.get("opora") or ""))

    up_eff = bool(d.get("use_previous_frame_resolved", False))
    forced = bool(d.get("forced_prev_chain_break"))
    prev_reason = str(d.get("prev_resolution_reason") or "").strip()
    pair_state = str(d.get("prev_pair_state") or "").strip()
    if idx == 0:
        d["ui_prev_line"] = "—"
    elif up_eff:
        d["ui_prev_line"] = "да (prev уходит в image API)"
    elif forced:
        d["ui_prev_line"] = "нет — принудительный разрыв continuity"
    else:
        d["ui_prev_line"] = "нет"
    if pair_state:
        d["ui_prev_line"] = f"{d['ui_prev_line']} · pair:{pair_state}"
    if prev_reason:
        d["ui_prev_line"] = f"{d['ui_prev_line']} · reason:{prev_reason}"
    is_key = bool(d.get("is_keyframe", True))
    k_reason = str(d.get("keyframe_reason") or "").strip()
    d["ui_keyframe_line"] = "key" if is_key else "non-key"
    if k_reason:
        d["ui_keyframe_line"] = f"{d['ui_keyframe_line']} · {k_reason}"

    # Окружение и prev взаимоисключающи в image API: при prev опора/пластина не подмешивается — в UI не показываем temple рядом с prev.
    if idx > 0 and up_eff:
        d["ui_env_line"] = "—"
    else:
        env_parts: list[str] = []
        if op:
            env_parts.append((op[:120] + "…") if len(op) > 120 else op)
        if br:
            env_parts.append(br)
        d["ui_env_line"] = " · ".join(env_parts) if env_parts else "—"
    # Совместимость со старыми шаблонами; в актуальном UI не используется.
    d["opora_display"] = d["ui_env_line"]


def lite_refs_summary_for_ui(ref_slots: list[dict[str, Any]]) -> str:
    """
    Одна строка для UI: что уходит в модель как изображения (порядок = порядок image_url в API).
    В текстовый промпт это не дублируем — картинки уже прикреплены.
    """
    if not ref_slots:
        return "нет изображений-референсов"
    parts: list[str] = []
    for s in ref_slots:
        if s.get("in_api") is False:
            continue
        role = str(s.get("role") or "")
        det = str(s.get("detail") or "").strip()
        pending = bool(s.get("pending"))
        pend = " (ещё нет файла)" if pending else ""
        if role == "environment":
            parts.append(f"пластина окружения{f' ({det})' if det else ''}{pend}")
        elif role in {"character", "dreamer"}:
            parts.append(f"лист персонажа{f' «{det}»' if det else ''}{pend}")
        elif role == "previous_frame":
            parts.append(f"предыдущий кадр{pend}")
        elif role == "extra_environment":
            parts.append(f"доп. окружение{f' ({det})' if det else ''}{pend}")
        else:
            parts.append(f"{str(s.get('label') or 'референс').strip()}{pend}")
    return ", ".join(parts) if parts else "нет изображений-референсов"


def lite_ref_slots_canonical_for_ui(
    frame_index: int,
    up_eff: bool,
    forced_break: bool,
    ref_slots: list[dict[str, Any]],
    ref_bundle: str,
) -> list[dict[str, Any]]:
    """
    Фиксированная схема для карточки: **0** — предыдущий кадр (всегда строка для кадров 2+),
    **1** — окружение (пластина или пояснение), далее персонажи. Поле **order** у реальных слотов —
    порядок в multipart; заглушки помечены **in_api: false**.
    """
    rb = str(ref_bundle or "")
    prev_src = [dict(s) for s in ref_slots if s.get("role") == "previous_frame"]
    env_src = [
        dict(s)
        for s in ref_slots
        if s.get("role") in ("environment", "extra_environment")
    ]
    char_src = [dict(s) for s in ref_slots if s.get("role") in {"character", "dreamer"}]
    out: list[dict[str, Any]] = []
    di = 0
    simple_bundle = rb in {"simple_dreamer_env_only", "simple_no_ref"}

    if frame_index == 0:
        out.append(
            {
                "order": 0,
                "display_index": 0,
                "role": "previous_frame_na",
                "tier": "muted",
                "label": "Предыдущий кадр (слот 0)",
                "detail": "для первого кадра не используется",
                "url": None,
                "pending": False,
                "in_api": False,
            }
        )
        di = 1
    else:
        if up_eff and prev_src and not simple_bundle:
            p0 = dict(prev_src[0])
            p0["display_index"] = 0
            p0["in_api"] = True
            out.append(p0)
            di = 1
        elif up_eff and not simple_bundle:
            out.append(
                {
                    "order": 0,
                    "display_index": 0,
                    "role": "previous_frame",
                    "tier": "continuity",
                    "label": "Предыдущий кадр (слот 0)",
                    "detail": "",
                    "url": None,
                    "pending": True,
                    "in_api": True,
                }
            )
            di = 1
        else:
            bits: list[str] = []
            if forced_break:
                bits.append("принудительный разрыв continuity")
            if not bits:
                bits.append("модель не запросила prev или ветка окружение+персонажи")
            out.append(
                {
                    "order": 0,
                    "display_index": 0,
                    "role": "previous_frame_skip",
                    "tier": "muted",
                    "label": "Предыдущий кадр (слот 0)",
                    "detail": "не в запросе · " + " · ".join(bits),
                    "url": None,
                    "pending": False,
                    "in_api": False,
                }
            )
            di = 1

    if env_src:
        for e in env_src:
            e = dict(e)
            e["display_index"] = di
            e["in_api"] = True
            out.append(e)
            di += 1
    elif not (up_eff and rb == "chain_prev_only"):
        out.append(
            {
                "order": 999,
                "display_index": di,
                "role": "environment_placeholder",
                "tier": "muted",
                "label": "Окружение (слот 1)",
                "detail": "пластина не сопоставлена",
                "url": None,
                "pending": False,
                "in_api": False,
            }
        )
        di += 1

    if char_src:
        for c in char_src:
            c = dict(c)
            if c.get("role") == "dreamer":
                c["role"] = "character"
            c["display_index"] = di
            c["in_api"] = True
            out.append(c)
            di += 1

    return out


def enrich_lite_frame_cards(
    cards: list[dict[str, Any]],
    *,
    step1_char_titles: list[str] | None = None,
) -> list[dict[str, Any]]:
    def _sanitize_self_contained_frame_text(text: str) -> tuple[str, list[str]]:
        t = (text or "").strip()
        if not t:
            return "", []
        warnings: list[str] = []
        patterns = [
            (r"\b(как в предыдущем кадре|как ранее|как раньше)\b[,. ]*", "в текущем кадре "),
            (r"\b(продолжает|продолжают)\b[,. ]*", ""),
            (r"\b(затем|дальше|после этого|снова это)\b[,. ]*", ""),
        ]
        out = t
        for pat, repl in patterns:
            new_out = re.sub(pat, repl, out, flags=re.IGNORECASE)
            if new_out != out:
                warnings.append(f"self_contained_fix:{pat}")
                out = new_out
        out = re.sub(r"\s+", " ", out).strip(" ,.;:-")
        return out, warnings

    out: list[dict[str, Any]] = []
    prior_for_chain: list[dict[str, Any]] = []
    titles = list(step1_char_titles or [])
    for i, c in enumerate(cards):
        if not isinstance(c, dict):
            continue
        d = dict(c)
        f = parse_frame_body_fields(str(d.get("body") or ""))
        d["opora"] = _strip_md_bold_noise(str(f.get("opora") or ""))
        d["izmenenie"] = _strip_md_bold_noise(str(f.get("izmenenie") or ""))
        if f.get("delta"):
            d["izmenenie"] = _strip_md_bold_noise(str(f.get("delta") or ""))
        kad = str(f.get("kad") or "")
        if f.get("frame_text"):
            kad = str(f.get("frame_text") or "")
        kad_clean = _strip_md_bold_noise(kad)
        kad_clean, self_contained_warnings = _sanitize_self_contained_frame_text(kad_clean)
        d["kad"] = kad_clean
        if self_contained_warnings:
            d["self_contained_warnings"] = list(self_contained_warnings)
        d["base_reference"] = str(f.get("base_reference") or "").strip()
        cr_raw = f.get("character_references") or ""
        if isinstance(cr_raw, str):
            d["character_references"] = _parse_character_references_list(cr_raw)
        else:
            d["character_references"] = []
        up_raw = f.get("use_previous_frame")
        if isinstance(up_raw, bool):
            d["use_previous_frame"] = up_raw
        elif isinstance(up_raw, str) and up_raw.strip():
            d["use_previous_frame"] = _parse_bool_loose(up_raw)
        else:
            d["use_previous_frame"] = None
        key_raw = f.get("is_keyframe")
        if isinstance(key_raw, bool):
            d["is_keyframe"] = key_raw
        elif isinstance(key_raw, str) and key_raw.strip():
            parsed_key = _parse_bool_loose(key_raw)
            d["is_keyframe"] = True if parsed_key is None else parsed_key
        else:
            d["is_keyframe"] = True
        d["keyframe_reason"] = _strip_md_bold_noise(str(f.get("keyframe_reason") or "")).strip()
        infer_missing_character_references(d, titles)
        if i > 0 and not list(d.get("character_references") or []):
            prev_d = out[-1]
            pc = list(prev_d.get("character_references") or [])
            if pc:
                d["character_references"] = _dedupe_lite_character_ids(
                    [str(x) for x in pc], titles
                )
                d["character_references_carried"] = True
        ensure_dreamer_in_frame_character_refs(d, titles)
        cr = [
            _canonical_lite_char_id(str(x), titles)
            for x in (d.get("character_references") or [])
            if _canonical_lite_char_id(str(x), titles)
        ]
        d["character_references"] = _dedupe_lite_character_ids(cr, titles)
        up_eff, forced_break = lite_resolve_use_previous_frame(
            d,
            i,
            prior_frame_entries=prior_for_chain,
            simple_mode=bool(d.get("simple_mode")),
        )
        d["use_previous_frame_resolved"] = up_eff
        d["forced_prev_chain_break"] = forced_break
        _append_lite_frame_ui_fields(i, d)
        prior_for_chain.append({"use_previous_frame_resolved": up_eff})
        out.append(d)

    logger.info("dream_lite шаг 2: обогащено кадров: %s", len(out))
    for j, d in enumerate(out):
        if not str(d.get("base_reference") or "").strip() and not str(d.get("opora") or "").strip():
            logger.warning(
                "dream_lite шаг 2: кадр %s %r без base_reference и без текста Опора",
                j,
                d.get("title"),
            )
    return out


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", " ", (s or "").lower(), flags=re.IGNORECASE).strip()


def _match_environment_url(
    opora: str,
    url_by_title: dict[str, str],
    titles_order: list[str],
) -> tuple[str | None, str]:
    """Возвращает (url, подпись для UI)."""
    if not url_by_title:
        return None, "нет сгенерированных окружений"
    n = _norm_key(opora)
    for t in titles_order:
        if t in url_by_title and _norm_key(t) and (_norm_key(t) in n or n in _norm_key(t)):
            return url_by_title[t], f"окружение «{t}»"
    for t, u in url_by_title.items():
        nt = _norm_key(t)
        if nt and (nt in n or n in nt):
            return u, f"окружение «{t}»"
    first_t = titles_order[0] if titles_order else next(iter(url_by_title.keys()))
    return url_by_title.get(first_t), f"окружение «{first_t}» (по умолчанию)"


def resolve_lite_env_url(
    ref_id: str,
    url_by_env: dict[str, str],
    env_order: list[str],
) -> tuple[str | None, str]:
    """Явный id окружения из раскадровки → URL этого run (не глобальный ref)."""
    rid = (ref_id or "").strip()
    if not rid:
        return None, "base_reference пуст"
    if rid in url_by_env:
        return url_by_env[rid], f"окружение «{rid}»"
    nk = _norm_key(rid)
    for t in env_order:
        if t in url_by_env and (_norm_key(t) == nk or nk in _norm_key(t) or _norm_key(t) in nk):
            return url_by_env[t], f"окружение «{t}»"
    for t, u in url_by_env.items():
        if nk and nk == _norm_key(t):
            return u, f"окружение «{t}»"
    return None, f"окружение «{rid}» не найдено в этом run"


def resolve_lite_char_url(
    ref_id: str,
    url_by_char: dict[str, str],
    char_order: list[str],
) -> str | None:
    rid = _normalize_lite_character_id_token(str(ref_id or ""))
    if not rid:
        return None
    if rid in url_by_char:
        return url_by_char[rid]
    nk = _norm_key(rid)
    for t in char_order:
        if rid == t or nk == _norm_key(t):
            return url_by_char.get(t)
    return None


def _is_dreamer_like_char_id(raw: str) -> bool:
    t = _norm_key(_normalize_lite_character_id_token(str(raw or "")))
    if not t:
        return False
    if t in {"dreamer", "protagonist"}:
        return True
    if t.startswith("dreamer_"):
        return True
    return "dream" in t


def _pick_simple_mode_dreamer_ref(
    *,
    card: dict[str, Any],
    url_by_char: dict[str, str],
    char_order: list[str],
) -> tuple[str | None, str]:
    """
    В simple mode non-prev используем один референс главного персонажа (Dreamer).
    Если Dreamer недоступен, не подмешиваем другого персонажа (strict simple mode).
    """
    refs = [str(x).strip() for x in list(card.get("character_references") or []) if str(x).strip()]
    for cid in refs:
        if _is_dreamer_like_char_id(cid):
            u = resolve_lite_char_url(cid, url_by_char, char_order)
            if u:
                return u, f"dreamer:{cid}"
    for title in char_order:
        if not _is_dreamer_like_char_id(title):
            continue
        u = url_by_char.get(title)
        if u:
            return u, f"dreamer:{title}"
    return None, "dreamer_unavailable"


LITE_PREVIEW_PREV_PLACEHOLDER = "__DREAM_LITE_PREVIEW_PREVIOUS_FRAME__"


def _lite_strip_preview_placeholder(urls: list[str]) -> list[str]:
    return [u for u in urls if u and u != LITE_PREVIEW_PREV_PLACEHOLDER]


def collect_lite_frame_reference_urls(
    frame_index: int,
    card: dict[str, Any],
    url_by_env: dict[str, str],
    env_order: list[str],
    url_by_char: dict[str, str],
    char_order: list[str],
    last_frame_url: str | None,
    *,
    prev_frame_title: str | None = None,
    use_previous_for_refs: bool,
    preview_mode: bool = False,
    simple_mode: bool = False,
) -> tuple[list[str], str, str, list[dict[str, Any]]]:
    """
    Собирает reference_image_urls для одного кадра.

    Цепочка (кадр 2+ и use_previous_frame): в multipart **только** предыдущий сгенерированный кадр —
    пластина окружения и листы персонажей не дублируются (опора уже в пикселях prev).

    Если предыдущего URL ещё нет и не режим превью-плана — fallback: env + персонажи.
    Кадр 0 или use_previous_frame=false: env + персонажи.

    `use_previous_for_refs` — итог scene-aware решения continuity (см. lite_resolve_use_previous_frame).

    `preview_mode`: если нужен предыдущий кадр, но URL ещё нет — ветка цепочки считается как выбранная,
    слот prev помечается pending; в списке URL для API плейсхолдер не возвращается.

    Возвращает (urls, ref_note, ref_bundle, ref_slots).
    ref_slots: порядок = порядок частей image_url в запросе; tier «base» | «secondary» для UI.
    """
    env_urls: list[str] = []
    env_notes: list[str] = []
    char_urls: list[str] = []
    extra_env_urls: list[str] = []
    extra_env_notes: list[str] = []

    use_prev = bool(use_previous_for_refs) and not bool(simple_mode)
    prev_u = (last_frame_url or "").strip()
    want_chain = use_prev and frame_index > 0
    prev_for_logic = prev_u
    placeholder_prev = bool(want_chain and not prev_u and preview_mode)
    if placeholder_prev:
        prev_for_logic = LITE_PREVIEW_PREV_PLACEHOLDER

    if want_chain and prev_for_logic:
        note = (
            f"только предыдущий кадр ({prev_frame_title})"
            if prev_frame_title
            else "только предыдущий кадр"
        )
        slots = [
            {
                "order": 1,
                "role": "previous_frame",
                "tier": "base_scene",
                "label": "Только предыдущий кадр (база непрерывности)",
                "detail": (prev_frame_title or "").strip(),
                "url": (prev_u or None) if prev_u else None,
                "pending": placeholder_prev,
            }
        ]
        return (
            _lite_strip_preview_placeholder([prev_for_logic]),
            note,
            "chain_prev_only",
            slots,
        )

    if simple_mode:
        env_pick_url: str | None = None
        env_pick_note = ""
        br = str(card.get("base_reference") or "").strip()
        if br:
            env_pick_url, env_pick_note = resolve_lite_env_url(br, url_by_env, env_order)
        if not env_pick_url:
            env_pick_url, env_pick_note = _match_environment_url(
                str(card.get("opora") or ""),
                url_by_env,
                env_order,
            )
        dreamer_url, dreamer_pick_note = _pick_simple_mode_dreamer_ref(
            card=card,
            url_by_char=url_by_char,
            char_order=char_order,
        )
        simple_urls: list[str] = []
        simple_slots: list[dict[str, Any]] = []
        order = 1
        note_parts: list[str] = []
        if env_pick_url:
            simple_urls.append(env_pick_url)
            simple_slots.append(
                {
                    "order": order,
                    "role": "environment",
                    "tier": "base_scene",
                    "label": "Окружение (simple mode)",
                    "detail": env_pick_note or "окружение",
                    "url": env_pick_url,
                    "pending": False,
                }
            )
            order += 1
            note_parts.append(f"env:{env_pick_note or 'matched'}")
        if dreamer_url:
            simple_urls.append(dreamer_url)
            simple_slots.append(
                {
                    "order": order,
                    "role": "dreamer",
                    "tier": "secondary",
                    "label": "Главный персонаж (Dreamer)",
                    "detail": dreamer_pick_note,
                    "url": dreamer_url,
                    "pending": False,
                }
            )
            note_parts.append(f"dreamer:{dreamer_pick_note}")
        deduped = _dedupe_ref_urls(simple_urls, _MAX_REF_URLS)
        if deduped:
            return (
                deduped,
                "simple mode: " + " · ".join(note_parts),
                "simple_dreamer_env_only",
                simple_slots,
            )
        return [], "simple mode: нет доступных env/dreamer референсов", "simple_no_ref", []

    br = str(card.get("base_reference") or "").strip()
    env_u: str | None = None
    env_note = ""
    if br:
        env_u, env_note = resolve_lite_env_url(br, url_by_env, env_order)
    if not env_u and frame_index == 0:
        env_u, env_note = _match_environment_url(
            str(card.get("opora") or ""),
            url_by_env,
            env_order,
        )
    if env_u:
        env_urls.append(env_u)
        env_notes.append(env_note)

    char_ids = _dedupe_str_list(
        [
            _normalize_lite_character_id_token(str(x))
            for x in (card.get("character_references") or [])
            if _normalize_lite_character_id_token(str(x))
        ]
    )
    max_chars = 3 if frame_index == 0 else 2
    cref: list[str] = []
    if char_ids:
        for cid in char_ids[:max_chars]:
            u = resolve_lite_char_url(str(cid), url_by_char, char_order)
            if u:
                cref.append(u)
    else:
        blob = f"{card.get('opora', '')} {card.get('izmenenie', '')} {card.get('kad', '')}"
        cref = _char_urls_for_shot(
            blob,
            url_by_char,
            char_order,
            max_n=max_chars,
            allow_fallback_all=frame_index == 0,
        )
    char_urls.extend(cref)

    if frame_index > 0:
        op_n = _norm_key(str(card.get("opora") or ""))
        if "предыдущ" not in op_n and (card.get("opora") or "").strip():
            u2, n2 = _match_environment_url(
                str(card.get("opora") or ""),
                url_by_env,
                env_order,
            )
            if u2:
                extra_env_urls.append(u2)
                extra_env_notes.append(n2)

    # Fallback без URL предыдущего кадра или use_previous_for_refs=false: только окружение и персонажи.
    core = env_urls + char_urls + extra_env_urls
    ref_urls = _dedupe_ref_urls(core, _MAX_REF_URLS)
    parts = env_notes + (["персонажи"] if char_urls else []) + extra_env_notes
    if use_previous_for_refs and frame_index > 0 and not prev_u:
        parts.append("fallback: нет файла предыдущего кадра")
    ref_note = " · ".join(parts) if parts else "без референсов"

    slots_std: list[dict[str, Any]] = []
    o = 1
    for eu, en in zip(env_urls, env_notes):
        slots_std.append(
            {
                "order": o,
                "role": "environment",
                "tier": "base_scene",
                "label": "Окружение (базовая пластина)",
                "detail": en,
                "url": eu,
                "pending": False,
            }
        )
        o += 1
    for j, cu in enumerate(char_urls):
        cid = str(char_ids[j]) if j < len(char_ids) else ""
        slots_std.append(
            {
                "order": o,
                "role": "character",
                "tier": "secondary",
                "label": "Персонаж (референс)",
                "detail": cid,
                "url": cu,
                "pending": False,
            }
        )
        o += 1
    for eu2, en2 in zip(extra_env_urls, extra_env_notes):
        slots_std.append(
            {
                "order": o,
                "role": "extra_environment",
                "tier": "secondary",
                "label": "Доп. окружение (по опоре кадра)",
                "detail": en2,
                "url": eu2,
                "pending": False,
            }
        )
        o += 1

    return ref_urls, ref_note, "standard", slots_std


def build_lite_frame_image_prompt(
    kad: str,
    izm: str,
    *,
    use_previous_for_refs: bool = False,
    simple_mode: bool = False,
    environment_label: str = "",
    dreamer_label: str = "",
) -> str:
    """
    Только человекочитаемое описание кадра для image API (текстовая часть после image_url):
    «Кадр» и «Изменение» из раскадровки, без служебных инструкций и без отдельного дисклеймера.
    """
    k = (kad or "").strip()
    z = (izm or "").strip()

    def _sanitize_image_prompt_text(src: str) -> str:
        s = (src or "").strip()
        if not s:
            return ""
        # Убираем прямую речь и глаголы говорения: это часто приводит к текстовым артефактам на изображении.
        s = re.sub(r"[\"«][^\"»]{1,220}[\"»]", "", s, flags=re.IGNORECASE)
        s = re.sub(
            r"\b(говорит|сказал(?:а|и)?|шепчет|шепнул(?:а|и)?|кричит|крикнул(?:а|и)?|произносит|реплика)\b[^.!?]{0,180}",
            "",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(r"\s+", " ", s).strip(" ,.;:-")
        return s

    def _rewrite_motion_to_still(src: str) -> str:
        s = (src or "").strip()
        if not s:
            return ""
        rules = [
            (r"\b(движется|двигается|ид[её]т|шагает|бежит)\b", "зафиксирована в фазе движения"),
            (r"\b(поворачивается|оборачивается)\b", "зафиксирована в моменте поворота"),
            (r"\b(поднимает|опускает)\b", "держит в зафиксированной позе"),
        ]
        out = s
        for pat, repl in rules:
            out = re.sub(pat, repl, out, flags=re.IGNORECASE)
        out = re.sub(r"\s+", " ", out).strip(" ,.;:-")
        return out

    k = _sanitize_image_prompt_text(k)
    z = _sanitize_image_prompt_text(z)
    k = _rewrite_motion_to_still(k)
    z = _rewrite_motion_to_still(z)
    if simple_mode:
        parts: list[str] = []
        env = (environment_label or "").strip()
        dr = (dreamer_label or "").strip()
        if env:
            parts.append(f"Окружение: {env}.")
        if dr:
            parts.append(f"Главный персонаж: {dr}.")
        if k:
            parts.append(f"Кадр: {k}")
        if z:
            parts.append(f"Изменение в кадре: {z}")
        parts.append("Режиссура: cinematic still, зафиксированный момент сцены, читаемая эмоция и поза.")
        parts.append(
            "Композиция: персонаж должен занимать осмысленную позицию в кадре (лево/центр/право, передний/средний/глубина), "
            "взаимодействовать со средой, ракурс живой, без эффекта непрерывного движения."
        )
        parts.append(
            "Анти-статичность: не reference-sheet look, не centered idle pose, не copied standing portrait."
        )
        parts.append("Если в референсах есть буквы/знаки, считай их шумом и не воспроизводи типографику в кадре.")
        base = " ".join(parts).strip() or "Кадр в заданном окружении с главным персонажем Dreamer."
    else:
        lines: list[str] = []
        if k:
            lines.append(k)
        if z:
            lines.append(z)
        base = "\n".join(lines) if lines else "Кадр по приложенным изображениям-референсам."
    safety = (
        "No text, no letters, no subtitles, no signs, no speech bubbles, no UI overlays, no logos, no watermark, no typography."
    )
    return f"{base}\n{safety}".strip()


def _simple_mode_labels_from_slots(ref_slots: list[dict[str, Any]]) -> tuple[str, str]:
    env_label = ""
    dreamer_label = ""
    for s in ref_slots:
        role = str(s.get("role") or "")
        detail = str(s.get("detail") or "").strip()
        if role in {"environment", "extra_environment"} and not env_label:
            env_label = detail
        if role in {"dreamer", "character"} and not dreamer_label:
            dreamer_label = detail
    return env_label, dreamer_label

_MAX_REF_URLS = 6


def _dedupe_ref_urls(urls: list[str], max_n: int = _MAX_REF_URLS) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = (u or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= max_n:
            break
    return out


def _char_urls_for_shot(
    blob: str,
    url_by_title: dict[str, str],
    order: list[str],
    *,
    max_n: int,
    allow_fallback_all: bool,
) -> list[str]:
    n = _norm_key(blob)
    picked: list[str] = []
    for t in order:
        u = url_by_title.get(t)
        if not u:
            continue
        nt = _norm_key(t)
        if not nt:
            continue
        if nt in n:
            picked.append(u)
            continue
        for word in nt.split():
            if len(word) > 2 and word in n:
                picked.append(u)
                break
    picked = _dedupe_ref_urls(picked, max_n)
    if picked or not allow_fallback_all:
        return picked
    out: list[str] = []
    for t in order:
        u = url_by_title.get(t)
        if u:
            out.append(u)
            if len(out) >= max_n:
                break
    return _dedupe_ref_urls(out, max_n)


def lite_make_bases_bundle(
    *,
    env_results: list[dict[str, Any]],
    char_results: list[dict[str, Any]],
    url_by_env: dict[str, str],
    url_by_char: dict[str, str],
    env_order: list[str],
    char_order: list[str],
    simple_mode: bool = False,
) -> dict[str, Any]:
    """Сериализуемый bundle после шага 3a: карты URL + результаты сеток для повторного показа в UI."""
    return {
        "url_by_env": dict(url_by_env),
        "url_by_char": dict(url_by_char),
        "env_order": list(env_order),
        "char_order": list(char_order),
        "env_results": list(env_results),
        "char_results": list(char_results),
        "simple_mode": bool(simple_mode),
    }


def lite_read_bases_bundle_from_json(data: Any) -> dict[str, Any]:
    """Разбор JSON шага 3a для шага 3b."""
    if not isinstance(data, dict):
        raise ValueError("bases_bundle должен быть объектом JSON")
    u_env = data.get("url_by_env")
    u_char = data.get("url_by_char")
    eo = data.get("env_order")
    co = data.get("char_order")
    if not isinstance(u_env, dict) or not isinstance(u_char, dict):
        raise ValueError("В bundle нужны url_by_env и url_by_char (объекты)")
    if not isinstance(eo, list) or not isinstance(co, list):
        raise ValueError("В bundle нужны env_order и char_order (массивы)")
    url_by_env = {str(k): str(v) for k, v in u_env.items() if v}
    url_by_char = {str(k): str(v) for k, v in u_char.items() if v}
    env_order = [str(x) for x in eo]
    char_order = [str(x) for x in co]
    env_results = list(data.get("env_results") or [])
    char_results = list(data.get("char_results") or [])
    simple_mode = bool(data.get("simple_mode"))
    return {
        "url_by_env": url_by_env,
        "url_by_char": url_by_char,
        "env_order": env_order,
        "char_order": char_order,
        "env_results": env_results,
        "char_results": char_results,
        "simple_mode": simple_mode,
    }


def run_lite_env_char_visual_chain(
    *,
    environments_text: str,
    image_model: str | None = None,
    simple_mode: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str], dict[str, str], list[str], list[str]]:
    """
    Банк референсов шага 1: сначала все персонажи, затем все окружения (порядок вызовов image API).
    Возвращает (env_results, char_results, url_by_env, url_by_char, env_order, char_order) — как раньше, для совместимости.
    """
    step1 = (environments_text or "").strip()
    env_cards, char_cards = split_lite_step1_world(step1)

    env_context_lines: list[str] = []
    for ec in env_cards[:3]:
        if not isinstance(ec, dict):
            continue
        et = str(ec.get("title") or "").strip()
        eb = str(ec.get("body") or "").strip()
        if et or eb:
            env_context_lines.append(f"{et}: {eb}".strip(": "))
    env_context = " | ".join(env_context_lines)[:1200]

    char_results: list[dict[str, Any]] = []
    url_by_char: dict[str, str] = {}
    char_order: list[str] = []

    dreamer_candidates = [
        idx
        for idx, cc in enumerate(char_cards)
        if _is_dreamer_like_char_id(str(cc.get("title") or "")) or _is_dreamer_like_char_id(str(cc.get("body") or ""))
    ]
    dreamer_idx = dreamer_candidates[0] if dreamer_candidates else (0 if char_cards else -1)

    for idx, c in enumerate(char_cards):
        title = str(c.get("title") or "").strip() or f"char_{len(char_results) + 1}"
        body = str(c.get("body") or "").strip()
        char_order.append(title)
        if bool(simple_mode) and idx != dreamer_idx:
            char_results.append(
                {
                    "title": title,
                    "ok": False,
                    "urls": [],
                    "error": "",
                    "generation_status": "skipped_simple_mode_non_dreamer",
                    "skip_reason": "simple_mode_dreamer_only_policy",
                    "skip_debug": {
                        "dreamer_idx": int(dreamer_idx),
                        "candidate_indices": list(dreamer_candidates),
                    },
                }
            )
            continue
        if not body:
            char_results.append(
                {
                    "title": title,
                    "ok": False,
                    "urls": [],
                    "error": "Пустое описание персонажа",
                }
            )
            continue
        prompt = (
            "Isolated human casting reference / model sheet: exactly one adult or clearly aged person, full figure or three-quarter, "
            "neutral relaxed stance, soft studio or plain background. "
            "Default casting requirement: European appearance. Face must be clearly visible, near-frontal, sharp focus. "
            "Outfit policy: if dream context implies climate/location constraints, choose practical clothing that fits environment; "
            "if casting notes explicitly require a conflicting outfit, keep casting notes as higher priority. "
            "Do not show interactions, second people, animals, crowds, or story action — even if the text below mentions them; "
            "render only this person's standalone appearance. "
            f"Environment context (for outfit only): {env_context}\n"
            f"Casting notes: {body}\n"
            "Readable face and silhouette, no text, no watermark, no non-human creature as subject."
        )
        tool_res = tool_generate_image_openrouter(
            prompt,
            model=image_model,
            aspect_ratio=LITE_OPENROUTER_IMAGE_ASPECT_RATIO,
            image_size=LITE_OPENROUTER_IMAGE_SIZE,
            strict_model=bool((image_model or "").strip()),
        )
        payload = tool_res.to_dict()
        ok = bool(payload.get("ok"))
        urls = list(payload.get("image_urls") or [])
        if urls:
            urls = urls[:1]
        err = None if ok else str(payload.get("error") or "Ошибка генерации")
        if ok and urls:
            url_by_char[title] = urls[0]
        char_results.append(
            {
                "title": title,
                "ok": ok,
                "urls": urls,
                "error": err,
            }
        )

    env_results: list[dict[str, Any]] = []
    url_by_title: dict[str, str] = {}
    titles_order: list[str] = []

    for c in env_cards:
        title = str(c.get("title") or "").strip() or f"env_{len(env_results) + 1}"
        body = str(c.get("body") or "").strip()
        titles_order.append(title)
        if not body:
            env_results.append(
                {
                    "title": title,
                    "ok": False,
                    "urls": [],
                    "error": "Пустое описание окружения",
                }
            )
            continue
        prompt = (
            "Environment plate for storyboard (simple mode): clean location-only scene, no living beings. "
            "Strictly no humans, animals, birds, insects, crowds, silhouettes, distant people, or biological creatures. "
            "Focus on architecture/landscape, materials, light, weather, color palette, and clear action zone. "
            if simple_mode
            else "Environment plate for storyboard: prefer human eye level, foreground and a clear focal zone for action; "
            "avoid empty abstract panorama unless the brief explicitly demands vast distance or panorama scale. "
        ) + (
            f"{body}\n"
            "Single coherent frame, high detail, coherent lighting, no text, no watermark."
        )
        tool_res = tool_generate_image_openrouter(
            prompt,
            model=image_model,
            aspect_ratio=LITE_OPENROUTER_IMAGE_ASPECT_RATIO,
            image_size=LITE_OPENROUTER_IMAGE_SIZE,
            strict_model=bool((image_model or "").strip()),
        )
        payload = tool_res.to_dict()
        ok = bool(payload.get("ok"))
        urls = list(payload.get("image_urls") or [])
        err = None if ok else str(payload.get("error") or "Ошибка генерации")
        if ok and urls:
            url_by_title[title] = urls[0]
        env_results.append(
            {
                "title": title,
                "ok": ok,
                "urls": urls,
                "error": err,
            }
        )

    return env_results, char_results, url_by_title, url_by_char, titles_order, char_order


def lite_frame_generation_plans(
    *,
    frames_text: str,
    url_by_env: dict[str, str],
    url_by_char: dict[str, str],
    env_order: list[str],
    char_order: list[str],
    frames_prev_link_raw: str | None = None,
    simple_mode: bool = False,
) -> list[dict[str, Any]]:
    """
    План по каждому кадру до вызова image API: промпт и слоты референсов.
    Файла предыдущего кадра ещё нет — для цепочки prev слот помечается pending (см. collect… preview_mode).
    Полный текст сна в image API не входит.
    """
    char_titles = [str(t).strip() for t in char_order if str(t).strip()]
    frame_cards = lite_frame_cards_for_visual_from_text(
        frames_text,
        step1_char_titles=char_titles,
        frames_prev_link_raw=frames_prev_link_raw,
    )
    plans: list[dict[str, Any]] = []
    synthetic_entries: list[dict[str, Any]] = []

    for i, c in enumerate(frame_cards):
        title = str(c.get("title") or f"Кадр {i + 1}").strip()
        opora = str(c.get("opora") or "")
        izm = str(c.get("izmenenie") or "")
        kad = str(c.get("kad") or "").strip()
        is_keyframe = bool(c.get("is_keyframe", True))
        keyframe_reason = str(c.get("keyframe_reason") or "").strip()
        prev_title = (
            str(frame_cards[i - 1].get("title") or f"кадр {i}") if i > 0 else None
        )
        up_eff, forced_break = lite_resolve_use_previous_frame(
            c,
            i,
            prior_frame_entries=synthetic_entries,
            simple_mode=bool(simple_mode),
        )
        ref_urls, ref_note, ref_bundle, ref_slots = collect_lite_frame_reference_urls(
            i,
            c,
            url_by_env,
            env_order,
            url_by_char,
            char_order,
            None,
            use_previous_for_refs=up_eff,
            prev_frame_title=prev_title,
            preview_mode=True,
            simple_mode=simple_mode,
        )
        br = str(c.get("base_reference") or "").strip()
        env_line = "—"
        if br:
            _, env_line = resolve_lite_env_url(br, url_by_env, env_order)
        elif ref_bundle in {"standard", "simple_dreamer_env_only"}:
            eu, en = _match_environment_url(str(c.get("opora") or ""), url_by_env, env_order)
            if eu:
                env_line = en

        chars_line = ", ".join(str(x) for x in (c.get("character_references") or [])) or "—"
        refs_summary_line = lite_refs_summary_for_ui(ref_slots)
        img_prompt = build_lite_frame_image_prompt(
            kad,
            izm,
            use_previous_for_refs=up_eff,
            simple_mode=simple_mode,
            environment_label=env_line if simple_mode else "",
            dreamer_label=chars_line if simple_mode else "",
        )

        plans.append(
            {
                "index": i,
                "title": title,
                "opora": opora,
                "img_prompt": img_prompt,
                "refs_summary_line": refs_summary_line,
                "ref_note": ref_note,
                "ref_bundle": ref_bundle,
                "ref_slots": lite_ref_slots_canonical_for_ui(
                    i,
                    up_eff,
                    forced_break,
                    ref_slots,
                    ref_bundle,
                ),
                "reference_image_urls_ui": lite_ref_urls_for_ui(list(ref_urls)),
                "base_reference": br,
                "environment_label": env_line,
                "character_references": list(c.get("character_references") or []),
                "characters_line": chars_line,
                "use_previous_frame": c.get("use_previous_frame"),
                "use_previous_frame_resolved": up_eff,
                "forced_prev_chain_break": forced_break,
                "prev_resolution_reason": str(c.get("prev_resolution_reason") or ""),
                "prev_pair_state": str(c.get("prev_pair_state") or ""),
                "is_keyframe": is_keyframe,
                "keyframe_reason": keyframe_reason,
                "generation_status": ("planned_generate" if (not simple_mode or is_keyframe) else "planned_skip_non_keyframe"),
                "simple_mode": bool(simple_mode),
            }
        )
        synthetic_entries.append({"use_previous_frame_resolved": up_eff})

    return plans


def run_lite_frame_visual_chain(
    *,
    frames_text: str,
    url_by_env: dict[str, str],
    url_by_char: dict[str, str],
    env_order: list[str],
    char_order: list[str],
    image_model: str | None = None,
    frames_prev_link_raw: str | None = None,
    simple_mode: bool = False,
) -> list[dict[str, Any]]:
    """Только кадры; url окружений/персонажей уже известны. Текст сна в промпт не добавляется."""
    char_titles = [str(t).strip() for t in char_order if str(t).strip()]
    frame_cards = lite_frame_cards_for_visual_from_text(
        frames_text,
        step1_char_titles=char_titles,
        frames_prev_link_raw=frames_prev_link_raw,
    )
    frame_results: list[dict[str, Any]] = []
    last_frame_url: str | None = None

    def _refs_for_external_api(urls: list[str]) -> list[str]:
        out: list[str] = []
        for u in list(urls or []):
            raw = str(u or "").strip()
            if not raw:
                continue
            resolved = lite_resolve_image_url_for_external_api(raw) or raw
            if resolved and resolved not in out:
                out.append(resolved)
        return out

    for i, c in enumerate(frame_cards):
        title = str(c.get("title") or f"Кадр {i + 1}").strip()
        opora = str(c.get("opora") or "")
        izm = str(c.get("izmenenie") or "")
        kad = str(c.get("kad") or "").strip()
        is_keyframe = bool(c.get("is_keyframe", True))
        keyframe_reason = str(c.get("keyframe_reason") or "").strip()
        prev_title = (
            str(frame_cards[i - 1].get("title") or f"кадр {i}") if i > 0 else None
        )
        prior_entries = frame_results
        up_eff, forced_break = lite_resolve_use_previous_frame(
            c,
            i,
            prior_frame_entries=prior_entries,
            simple_mode=bool(simple_mode),
        )
        ref_urls, ref_note, ref_bundle, ref_slots = collect_lite_frame_reference_urls(
            i,
            c,
            url_by_env,
            env_order,
            url_by_char,
            char_order,
            last_frame_url if up_eff else None,
            use_previous_for_refs=up_eff,
            prev_frame_title=prev_title,
            simple_mode=simple_mode,
        )
        ref_urls_for_api = _refs_for_external_api(ref_urls)
        env_label_from_slots, dreamer_label_from_slots = _simple_mode_labels_from_slots(ref_slots)
        br = str(c.get("base_reference") or "").strip()
        env_line = "—"
        if br:
            _, env_line = resolve_lite_env_url(br, url_by_env, env_order)
        elif ref_bundle in {"standard", "simple_dreamer_env_only"}:
            eu, en = _match_environment_url(str(c.get("opora") or ""), url_by_env, env_order)
            if eu:
                env_line = en
        chars_line = ", ".join(str(x) for x in (c.get("character_references") or [])) or "—"
        dreamer_line = dreamer_label_from_slots or chars_line
        img_prompt = build_lite_frame_image_prompt(
            kad,
            izm,
            use_previous_for_refs=up_eff,
            simple_mode=simple_mode,
            environment_label=env_label_from_slots or (env_line if simple_mode else ""),
            dreamer_label=dreamer_line if simple_mode else "",
        )
        canonical_slots = lite_ref_slots_canonical_for_ui(
            i,
            up_eff,
            forced_break,
            ref_slots,
            ref_bundle,
        )
        refs_summary_line = lite_refs_summary_for_ui(canonical_slots)

        if simple_mode and not is_keyframe:
            frame_results.append(
                {
                    "index": i,
                    "title": title,
                    "opora": opora or ("окружение" if i == 0 else "предыдущий кадр"),
                    "izmenenie": izm,
                    "kad": kad,
                    "refs_summary_line": refs_summary_line,
                    "base_reference": str(c.get("base_reference") or ""),
                    "environment_label": env_line,
                    "characters_line": chars_line,
                    "character_references": list(c.get("character_references") or []),
                    "use_previous_frame": c.get("use_previous_frame"),
                    "use_previous_frame_resolved": up_eff,
                    "forced_prev_chain_break": forced_break,
                    "prev_resolution_reason": str(c.get("prev_resolution_reason") or ""),
                    "prev_pair_state": str(c.get("prev_pair_state") or ""),
                    "is_keyframe": False,
                    "keyframe_reason": keyframe_reason,
                    "simple_mode": bool(simple_mode),
                    "ref_bundle": ref_bundle,
                    "ref_slots": canonical_slots,
                    "img_prompt": "",
                    "reference_image_urls": list(ref_urls),
                    "reference_image_urls_ui": lite_ref_urls_for_ui(ref_urls),
                    "refs_sent_count": len(ref_urls_for_api),
                    "refs_sent_roles": [str(s.get("role") or "") for s in list(ref_slots or []) if s.get("in_api", True) is not False],
                    "refs_policy_result": ("simple_dreamer_env_only" if bool(simple_mode) else "standard_frame_refs"),
                    "image_model": str(image_model or "").strip(),
                    "requested_model": str(image_model or "").strip(),
                    "selected_model": str(image_model or "").strip(),
                    "effective_model": str(image_model or "").strip(),
                    "openrouter_models_tried": [],
                    "primary_model_error": "",
                    "ok": False,
                    "urls": [],
                    "error": "",
                    "ref_note": ref_note,
                    "generation_status": "skipped_non_keyframe",
                    "image_generated_ok": False,
                    "usage_unavailable": True,
                }
            )
            continue

        request_ts = time.time()
        tool_res = tool_generate_image_openrouter(
            img_prompt.strip(),
            reference_image_urls=ref_urls_for_api if ref_urls_for_api else None,
            model=image_model,
            aspect_ratio=LITE_OPENROUTER_IMAGE_ASPECT_RATIO,
            image_size=LITE_OPENROUTER_IMAGE_SIZE,
            strict_model=bool((image_model or "").strip()),
        )
        first_response_ts = time.time()
        payload = tool_res.to_dict()
        completed_ts = time.time()
        ok = bool(payload.get("ok"))
        urls = list(payload.get("image_urls") or [])
        err = None if ok else str(payload.get("error") or "Ошибка генерации")
        requested_model = str(image_model or "").strip()
        model_used = str(payload.get("model") or "").strip() or (image_model or "")
        models_tried = [str(x).strip() for x in list(payload.get("models_tried") or []) if str(x).strip()]
        primary_error = ""
        if err and models_tried and requested_model and models_tried[0] != model_used:
            primary_error = err
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        tokens_in = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        tokens_out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (tokens_in + tokens_out) or 0)
        estimated_cost_usd = None
        usage_unavailable = not bool(usage)
        if ok and urls:
            last_frame_url = urls[0]
        frame_results.append(
            {
                "index": i,
                "title": title,
                "opora": opora or ("окружение" if i == 0 else "предыдущий кадр"),
                "izmenenie": izm,
                "kad": kad,
                "refs_summary_line": refs_summary_line,
                "base_reference": str(c.get("base_reference") or ""),
                "environment_label": env_line,
                "characters_line": chars_line,
                "character_references": list(c.get("character_references") or []),
                "use_previous_frame": c.get("use_previous_frame"),
                "use_previous_frame_resolved": up_eff,
                "forced_prev_chain_break": forced_break,
                "prev_resolution_reason": str(c.get("prev_resolution_reason") or ""),
                "prev_pair_state": str(c.get("prev_pair_state") or ""),
                "is_keyframe": is_keyframe,
                "keyframe_reason": keyframe_reason,
                "simple_mode": bool(simple_mode),
                "ref_bundle": ref_bundle,
                "ref_slots": canonical_slots,
                "img_prompt": img_prompt,
                "reference_image_urls": list(ref_urls),
                "reference_image_urls_ui": lite_ref_urls_for_ui(ref_urls),
                "refs_sent_count": len(ref_urls_for_api),
                "refs_sent_roles": [str(s.get("role") or "") for s in list(ref_slots or []) if s.get("in_api", True) is not False],
                "refs_policy_result": ("simple_dreamer_env_only" if bool(simple_mode) else "standard_frame_refs"),
                "image_model": model_used,
                "requested_model": requested_model,
                "selected_model": requested_model,
                "effective_model": model_used,
                "openrouter_models_tried": models_tried,
                "primary_model_error": primary_error,
                "ok": ok,
                "urls": urls,
                "error": err,
                "ref_note": ref_note,
                "generation_status": ("generated" if ok else "error"),
                "image_generated_ok": bool(ok and urls),
                "request_at": request_ts,
                "first_response_at": first_response_ts,
                "completed_at": completed_ts,
                "duration_ms": int((completed_ts - request_ts) * 1000),
                "provider_latency_ms": int((first_response_ts - request_ts) * 1000),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "total_tokens": total_tokens,
                "estimated_cost_usd": estimated_cost_usd,
                "usage_unavailable": usage_unavailable,
            }
        )

    return frame_results


def run_lite_visual_generation_chain(
    *,
    environments_text: str,
    frames_text: str,
    dream_text: str = "",
    image_model: str | None = None,
    frames_prev_link_raw: str | None = None,
    simple_mode: bool = False,
) -> dict[str, Any]:
    """
    Полный шаг 1 в `environments_text` (## Окружения + ## Персонажи).
    Порядок: все персонажи → все окружения → кадры 1..N (refs: env+chars или только prev при цепочке).
    """
    env_results, char_results, url_by_title, url_by_char, titles_order, char_order = (
        run_lite_env_char_visual_chain(
            environments_text=environments_text,
            image_model=image_model,
            simple_mode=simple_mode,
        )
    )
    frame_results = run_lite_frame_visual_chain(
        frames_text=frames_text,
        url_by_env=url_by_title,
        url_by_char=url_by_char,
        env_order=titles_order,
        char_order=char_order,
        image_model=image_model,
        frames_prev_link_raw=frames_prev_link_raw,
        simple_mode=simple_mode,
    )

    return {
        "env_results": env_results,
        "char_results": char_results,
        "frame_results": frame_results,
        "simple_mode": bool(simple_mode),
    }


def run_lite_i2v_concat_to_mp4(
    *,
    transition_plan: dict[str, Any],
    frame_results: list[dict[str, Any]],
    owner_user_id: str,
    output_basename: str,
    lite_run_tag: str | None = None,
    prompt_mode: str = "first_last_frame",
) -> dict[str, Any]:
    """
    Очередь i2v по animate_transition (tool_image_to_video + poll) и склейка mp4 (ffmpeg).
    Не использует LLM-tools: вызовы видео API идут из кода пайплайна.
    """
    from services.tools.video_tools import get_video_job_service, tool_image_to_video
    from services.video.final_video_assembler import FinalVideoAssemblerError, assemble_remote_mp4s

    tag = lite_run_tag or uuid.uuid4().hex[:12]
    segments = lite_collect_animate_i2v_segments(transition_plan, frame_results, prompt_mode=prompt_mode)
    if not segments:
        return {
            "final_video_url": None,
            "error": (
                "Нет сегментов animate_transition с двумя успешными кадрами — нечего анимировать. "
                "В плане монтажа нужны переходы типа animate_transition между кадрами с готовыми картинками."
            ),
            "clips": [],
        }

    svc = get_video_job_service()
    video_urls: list[str] = []
    clips: list[dict[str, Any]] = []

    for i, seg in enumerate(segments):
        iu_raw = str(seg.get("image_url") or "").strip()
        lf_raw = str(seg.get("last_frame_url") or "").strip() or None
        iu = lite_resolve_image_url_for_external_api(iu_raw) or iu_raw
        lf_r = lite_resolve_image_url_for_external_api(lf_raw) if lf_raw else None
        prompt = (
            "Cinematic motion between storyboard keyframes, same characters and space, coherent light. "
            f"{seg.get('motion_prompt') or ''}\n"
            "No text or subtitles on screen."
        ).strip()
        payload = tool_image_to_video(
            prompt=prompt,
            image_url=iu,
            duration=4,
            resolution="720p",
            owner_user_id=owner_user_id,
            last_frame_url=lf_r,
            job_extra={
                "dream_lite_one_shot": tag,
                "dream_lite_segment_index": i,
            },
        )
        entry: dict[str, Any] = {
            "segment_index": i,
            "from_frame_index": seg.get("from_frame_index"),
            "to_frame_index": seg.get("to_frame_index"),
            "job_id": payload.get("job_id"),
            "ok": bool(payload.get("ok")),
            "error": payload.get("error"),
            "video_url": None,
            "status": None,
        }
        jid = payload.get("job_id")
        if jid and payload.get("ok"):
            try:
                job = svc.poll_job_until_done(str(jid), timeout_sec=2400.0, interval_sec=3.0)
            except TimeoutError:
                entry["error"] = "Таймаут ожидания video job"
                entry["status"] = "timeout"
                clips.append(entry)
                continue
            entry["status"] = job.get("status")
            vu = job.get("video_url")
            entry["video_url"] = vu
            if job.get("error"):
                entry["error"] = job.get("error")
            if job.get("status") == "succeeded" and vu:
                video_urls.append(str(vu).strip())
        clips.append(entry)

    if not video_urls:
        return {
            "final_video_url": None,
            "error": (
                "Не получено ни одного готового клипа i2v. Проверьте "
                "VIDEO_GENERATION_BACKEND / ключи Wan или OpenRouter Video и коллекцию video_jobs."
            ),
            "clips": clips,
        }

    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", (output_basename or "").strip()) or f"one_shot_{tag}.mp4"
    if not safe.endswith(".mp4"):
        safe += ".mp4"
    out_dir = _lite_dev_static_root() / "dream_lite_final"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / safe
    public_url = f"/dev/static/dream_lite_final/{safe}"

    try:
        assemble_remote_mp4s(video_urls, out_path)
    except FinalVideoAssemblerError as e:
        logger.warning("dream_lite i2v concat: ffmpeg: %s", e)
        return {
            "final_video_url": None,
            "error": str(e),
            "clips": clips,
        }

    return {
        "final_video_url": public_url,
        "error": None,
        "clips": clips,
        "concat_source_urls": video_urls,
    }


async def lite_chat_text(openai: Any, *, system: str, user: str) -> str:
    """Один вызов chat.completions, возвращает текст ассистента."""
    resp = await openai.chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    choice = resp.choices[0]
    msg = choice.message
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts).strip()
    return ""
