"""Быстрый локальный тест PromptStore без API."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from prompt_store import PromptStore


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        p, d = tmp / "prompts", tmp / "data"
        p.mkdir()
        d.mkdir()
        (p / "system.txt").write_text("BASE\n", encoding="utf-8")
        s = PromptStore(p, d)
        assert s.read_system_prompt() == "BASE"
        s.update_system_prompt("OVERRIDE v1")
        assert s.read_system_prompt() == "OVERRIDE v1"
        s.update_system_prompt("OVERRIDE v2")
        assert s.read_system_prompt() == "OVERRIDE v2"
        assert list((d / "backups").glob("system_*.txt")), "backup missing"
        s.reset_to_default()
        assert s.read_system_prompt() == "BASE"
        s.append_history(1, "user", "hi")
        s.append_history(1, "assistant", "hey")
        assert len(s.load_history(1)) == 2
        s.clear_history(1)
        assert s.load_history(1) == []
        print("PROMPT_STORE_OK")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
