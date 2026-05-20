"""
Playground: визуальная раскадровка после плана режиссёра (без Mongo / Telegram).

Порядок: глобальные референсы (environment → character → object) → ключевые кадры по frame_index.
Для кадров: опционально предыдущий кадр + сгенерированные ref_id из uses_reference_ids.
"""
from __future__ import annotations

import logging
from typing import Any

from services.tools.openrouter_image_tools import tool_generate_image_openrouter

logger = logging.getLogger(__name__)

_KIND_ORDER = ("environment", "character", "object")

_CONTINUITY_HINT = (
    "\n\nВизуальная непрерывность: опирайся на приложенные изображения как на опору. "
    "Тот же мир, те же персонажи и масштаб; изменилось только действие или момент кадра — как следующая панель комикса."
)

_MAX_REF_IMAGES = 6


def _as_dict(x: Any) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _as_list(x: Any) -> list[Any]:
    return x if isinstance(x, list) else []


def _ordered_global_refs(items_in: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in _KIND_ORDER}
    rest: list[dict[str, Any]] = []
    for it in items_in:
        if not isinstance(it, dict):
            continue
        k = str(it.get("kind") or "").strip().lower()
        if k in buckets:
            buckets[k].append(it)
        else:
            rest.append(it)
    out: list[dict[str, Any]] = []
    for k in _KIND_ORDER:
        out.extend(buckets[k])
    out.extend(rest)
    return out


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = (u or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out[:_MAX_REF_IMAGES]


def _existing_preview_url(item: dict[str, Any]) -> str | None:
    u = str(item.get("preview_image_url") or "").strip()
    if u.startswith("http://") or u.startswith("https://") or u.startswith("data:"):
        return u
    return None


def run_director_storyboard_pipeline(director: dict[str, Any]) -> dict[str, Any]:
    """
    Возвращает словарь для шаблона: ref_results, keyframe_results, notice (optional).
    """
    d = _as_dict(director)
    gref = _as_dict(d.get("global_references"))
    kf_block = _as_dict(d.get("key_frames"))

    ref_items_in = [x for x in _as_list(gref.get("items")) if isinstance(x, dict)]
    ref_items = _ordered_global_refs(ref_items_in)

    url_by_ref_id: dict[str, str] = {}
    ref_results: list[dict[str, Any]] = []

    for it in ref_items:
        rid = str(it.get("ref_id") or "").strip() or f"ref_{len(ref_results) + 1}"
        label = str(it.get("label") or rid).strip()
        kind = str(it.get("kind") or "").strip()
        prompt = str(
            it.get("generation_prompt") or it.get("image_prompt") or it.get("prompt") or ""
        ).strip()

        existing = _existing_preview_url(it)
        if existing:
            url_by_ref_id[rid] = existing
            ref_results.append(
                {
                    "ref_id": rid,
                    "label": label,
                    "kind": kind,
                    "ok": True,
                    "skipped": True,
                    "urls": [existing],
                    "error": None,
                }
            )
            continue

        if not prompt:
            ref_results.append(
                {
                    "ref_id": rid,
                    "label": label,
                    "kind": kind,
                    "ok": False,
                    "skipped": False,
                    "urls": [],
                    "error": "Пустой generation_prompt",
                }
            )
            continue

        tool_res = tool_generate_image_openrouter(prompt)
        payload = tool_res.to_dict()
        ok = bool(payload.get("ok"))
        urls = list(payload.get("image_urls") or [])
        err = None if ok else str(payload.get("error") or "Ошибка генерации")
        if ok and urls:
            url_by_ref_id[rid] = urls[0]
        ref_results.append(
            {
                "ref_id": rid,
                "label": label,
                "kind": kind,
                "ok": ok,
                "skipped": False,
                "urls": urls,
                "error": err,
            }
        )

    kf_items_raw = [x for x in _as_list(kf_block.get("items")) if isinstance(x, dict)]

    def _fi(x: dict[str, Any]) -> int:
        try:
            return int(x.get("frame_index") or 0)
        except (TypeError, ValueError):
            return 0

    kf_items = sorted(kf_items_raw, key=_fi)
    kf_url_by_index: dict[int, str] = {}
    keyframe_results: list[dict[str, Any]] = []
    last_kf_url: str | None = None

    for kf in kf_items:
        fi = _fi(kf)
        if fi <= 0:
            fi = len(keyframe_results) + 1
        label = str(kf.get("short_label") or kf.get("moment_description") or f"Кадр {fi}")[:120]
        prompt = str(kf.get("image_prompt") or "").strip()
        if not prompt:
            keyframe_results.append(
                {
                    "frame_index": fi,
                    "label": label,
                    "ok": False,
                    "urls": [],
                    "error": "Пустой image_prompt",
                    "refs_used": [],
                }
            )
            continue

        boundary = str(kf.get("scene_boundary") or "").strip().lower()
        use_previous_kf = fi > 1 and boundary != "new_scene"

        ref_urls: list[str] = []
        refs_used: list[str] = []

        cf = kf.get("continues_from_frame_index")
        prev_from_map: str | None = None
        if cf is not None:
            try:
                ci = int(cf)
                prev_from_map = kf_url_by_index.get(ci)
            except (TypeError, ValueError):
                prev_from_map = None

        if prev_from_map:
            ref_urls.append(prev_from_map)
            refs_used.append(f"кадр #{cf}")
        elif use_previous_kf and last_kf_url:
            ref_urls.append(last_kf_url)
            refs_used.append("предыдущий кадр")

        for rid in _as_list(kf.get("uses_reference_ids")):
            rids = str(rid).strip()
            if not rids:
                continue
            u = url_by_ref_id.get(rids)
            if u:
                ref_urls.append(u)
                refs_used.append(f"ref:{rids}")

        ref_urls = _dedupe_urls(ref_urls)

        full_prompt = prompt
        if ref_urls:
            full_prompt = prompt + _CONTINUITY_HINT

        tool_res = tool_generate_image_openrouter(full_prompt, reference_image_urls=ref_urls or None)
        payload = tool_res.to_dict()
        ok = bool(payload.get("ok"))
        urls = list(payload.get("image_urls") or [])
        err = None if ok else str(payload.get("error") or "Ошибка генерации")
        if ok and urls:
            kf_url_by_index[fi] = urls[0]
            last_kf_url = urls[0]
        keyframe_results.append(
            {
                "frame_index": fi,
                "label": label,
                "ok": ok,
                "urls": urls,
                "error": err,
                "refs_used": refs_used,
            }
        )

    notice = (
        f"Референсов в плане: {len(ref_items)}, кадров: {len(kf_items)}. "
        "Кадры идут по возрастанию frame_index; к предыдущему кадру цепляется, "
        "если scene_boundary не new_scene или задан continues_from_frame_index."
    )

    return {
        "ref_results": ref_results,
        "keyframe_results": keyframe_results,
        "notice": notice,
    }
