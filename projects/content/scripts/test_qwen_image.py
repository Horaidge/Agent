#!/usr/bin/env python3
"""
Ручная проверка Qwen Image API без LLM.

Примеры:
  python scripts/test_qwen_image.py --prompt "A red apple on a wooden table"
  python scripts/test_qwen_image.py --prompt "..." --out-json data/qwen_last.json
  python scripts/test_qwen_image.py --edit-image ./tests/fixtures/sample.png --instruction "Make the sky purple"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Корень проекта в PYTHONPATH
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / "env")
    load_dotenv(_ROOT / ".env")
    load_dotenv(_ROOT / "ENV")
except ImportError:
    pass

from services.images.qwen_image_client import (  # noqa: E402
    QwenImageClientError,
    edit_image_with_instruction,
    generate_image_from_prompt,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(description="Тест Qwen Image (DashScope)")
    p.add_argument("--prompt", type=str, default="A simple blue circle on white background")
    p.add_argument(
        "--edit-image",
        type=str,
        default=None,
        help="Путь к файлу, https URL или data URI для edit_image_with_instruction",
    )
    p.add_argument(
        "--instruction",
        type=str,
        default="Enhance contrast slightly, keep composition.",
        help="Инструкция для режима --edit-image",
    )
    p.add_argument("--size", type=str, default="1024*1536")
    p.add_argument("--model", type=str, default="qwen-image-2.0")
    p.add_argument("--n", type=int, default=1)
    p.add_argument(
        "--out-json",
        type=str,
        default=None,
        help="Сохранить ответ (URL и метаданные) в JSON",
    )
    args = p.parse_args()

    try:
        if args.edit_image:
            print("Режим: edit_image_with_instruction", flush=True)
            urls = edit_image_with_instruction(
                image_source=args.edit_image,
                instruction=args.instruction,
                size=args.size,
                model=args.model,
                n=args.n,
            )
        else:
            print("Режим: generate_image_from_prompt", flush=True)
            urls = generate_image_from_prompt(
                prompt=args.prompt,
                size=args.size,
                model=args.model,
                n=args.n,
            )
    except QwenImageClientError as e:
        logging.error("Ошибка API: %s", e)
        return 1

    print("URL изображений:", flush=True)
    for u in urls:
        print(u, flush=True)

    record = {
        "mode": "edit" if args.edit_image else "generate",
        "prompt": args.prompt if not args.edit_image else None,
        "edit_image": args.edit_image,
        "instruction": args.instruction if args.edit_image else None,
        "size": args.size,
        "model": args.model,
        "n": args.n,
        "image_urls": urls,
    }
    out_path = args.out_json
    if not out_path:
        out_path = str(_ROOT / "data" / "runtime" / "qwen_image_last_test.json")
    path = Path(out_path)
    _write_json(path, record)
    print(f"Сохранено: {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
