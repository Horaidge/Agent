from __future__ import annotations

import difflib
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.config.settings import get_settings


def _runtime_dir() -> Path:
    p = get_settings().data_dir / "runtime"
    p.mkdir(parents=True, exist_ok=True)
    return p


def beat_planner_log_path() -> Path:
    return _runtime_dir() / "beat_planner_runs.jsonl"


def append_beat_planner_run(payload: dict[str, Any]) -> dict[str, Any]:
    system_prompt = _to_text(payload.get("system_prompt"))
    user_input = _to_text(payload.get("user_input"))
    assembled_prompt = _to_text(payload.get("assembled_prompt"))
    raw_response = _to_text(payload.get("raw_response"))
    row = {
        "run_id": str(payload.get("run_id") or uuid4()),
        "ts": datetime.now(UTC).isoformat(),
        "hashes": {
            "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            "user_input_sha256": hashlib.sha256(user_input.encode("utf-8")).hexdigest(),
            "assembled_prompt_sha256": hashlib.sha256(assembled_prompt.encode("utf-8")).hexdigest(),
            "raw_response_sha256": hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),
        },
        **payload,
    }
    with beat_planner_log_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_latest_beat_planner_runs(limit: int = 2) -> list[dict[str, Any]]:
    p = beat_planner_log_path()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    if not rows:
        return []
    return rows[-limit:]


def _to_text(v: Any) -> str:
    if isinstance(v, str):
        return v
    if v is None:
        return ""
    try:
        return json.dumps(v, ensure_ascii=False, indent=2)
    except Exception:
        return str(v)


def _mk_diff(a: str, b: str, from_name: str, to_name: str) -> str:
    out = difflib.unified_diff(
        a.splitlines(),
        b.splitlines(),
        fromfile=from_name,
        tofile=to_name,
        lineterm="",
    )
    txt = "\n".join(out).strip()
    return txt or "NO_DIFF"


def diff_last_two_runs() -> dict[str, Any]:
    runs = read_latest_beat_planner_runs(limit=2)
    if len(runs) < 2:
        return {
            "ok": False,
            "reason": "Недостаточно запусков для сравнения (нужно минимум 2).",
            "runs": runs,
        }
    a, b = runs[-2], runs[-1]
    a_id = str(a.get("run_id") or "run_A")
    b_id = str(b.get("run_id") or "run_B")
    return {
        "ok": True,
        "run_a": a,
        "run_b": b,
        "diffs": {
            "system_prompt": _mk_diff(
                _to_text(a.get("system_prompt")),
                _to_text(b.get("system_prompt")),
                f"{a_id}:system_prompt",
                f"{b_id}:system_prompt",
            ),
            "user_input": _mk_diff(
                _to_text(a.get("user_input")),
                _to_text(b.get("user_input")),
                f"{a_id}:user_input",
                f"{b_id}:user_input",
            ),
            "assembled_prompt": _mk_diff(
                _to_text(a.get("assembled_prompt")),
                _to_text(b.get("assembled_prompt")),
                f"{a_id}:assembled_prompt",
                f"{b_id}:assembled_prompt",
            ),
            "raw_response": _mk_diff(
                _to_text(a.get("raw_response")),
                _to_text(b.get("raw_response")),
                f"{a_id}:raw_response",
                f"{b_id}:raw_response",
            ),
        },
    }
