"""
Ручной тест image-to-video (Wan): создаёт job, ждёт завершения по Mongo, пишет JSON.

Переменные окружения: DASHSCOPE_API_KEY, MONGODB_URI (как в проекте).

Пример:
  python scripts/test_wan_video.py ^
    --image-url https://cdn.translate.alibaba.com/r/wanx-demo-1.png ^
    --prompt "A cat running on the grass"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# корень проекта в sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config.settings import get_settings
from services.tools.video_tools import get_video_job_service, tool_image_to_video


def main() -> int:
    parser = argparse.ArgumentParser(description="Тест Wan image-to-video (async job)")
    parser.add_argument(
        "--image-url",
        required=True,
        help="Публичный URL или data URI первого кадра (first_frame)",
    )
    parser.add_argument(
        "--last-frame-url",
        default=None,
        help="Опционально: URL/data URI конечного кадра (wan2.7 last_frame)",
    )
    parser.add_argument("--prompt", required=True, help="Текстовый промпт")
    parser.add_argument("--duration", type=int, default=4)
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--model", default="wan2.7-i2v")
    parser.add_argument(
        "--timeout",
        type=float,
        default=1200.0,
        help="Секунд ожидания завершения job в Mongo",
    )
    args = parser.parse_args()

    settings = get_settings()
    out_path = settings.data_dir / "runtime" / "wan_video_test.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    created = tool_image_to_video(
        prompt=args.prompt,
        image_url=args.image_url,
        duration=args.duration,
        resolution=args.resolution,
        model=args.model,
        owner_user_id="test_wan_script",
        last_frame_url=args.last_frame_url,
    )
    job_id = created.get("job_id")
    if not job_id:
        payload = {
            "tool_result": created,
            "elapsed_sec": time.perf_counter() - t0,
            "error": "job_id не получен",
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 1

    print("job_id:", job_id)
    print("первичный ответ tool:", json.dumps(created, ensure_ascii=False, indent=2))

    svc = get_video_job_service()
    try:
        final = svc.poll_job_until_done(job_id, timeout_sec=args.timeout)
    except TimeoutError as e:
        elapsed = time.perf_counter() - t0
        payload = {
            "tool_result": created,
            "job_id": job_id,
            "error": str(e),
            "elapsed_sec": elapsed,
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print("TIMEOUT", e)
        return 1

    elapsed = time.perf_counter() - t0
    payload = {
        "tool_result": created,
        "job_id": job_id,
        "final_job": final,
        "elapsed_sec": round(elapsed, 3),
        "video_url": final.get("video_url"),
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print("готово, сек:", round(elapsed, 2))
    print("video_url:", final.get("video_url"))
    print("результат записан:", out_path)
    return 0 if final.get("status") == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
