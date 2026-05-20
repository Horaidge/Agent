"""
Проверка вызова OpenRouter image generation (как в Сборщике).

Требуется OPENROUTER_API_KEY в окружении или в .env проекта.

Пример:
  cd projects/content && python scripts/test_openrouter_image.py --prompt "A red cube on white"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config.settings import get_settings
from services.tools.openrouter_image_tools import tool_generate_image_openrouter


def main() -> int:
    parser = argparse.ArgumentParser(description="Тест OpenRouter image (Nano Banana / Gemini image)")
    parser.add_argument("--prompt", default="A simple red cube on white background, product photo.")
    parser.add_argument("--aspect-ratio", default=None, help="например 16:9")
    parser.add_argument("--model", default=None, help="override OPENROUTER_IMAGE_MODEL")
    args = parser.parse_args()

    settings = get_settings()
    if not (settings.openrouter_api_key or "").strip():
        print("Ошибка: задайте OPENROUTER_API_KEY в окружении или .env", file=sys.stderr)
        return 1

    res = tool_generate_image_openrouter(
        args.prompt,
        aspect_ratio=args.aspect_ratio,
        model=args.model,
    )
    out_path = settings.data_dir / "runtime" / "openrouter_image_test.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = res.to_dict()
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    print("записано:", out_path)
    return 0 if res.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
