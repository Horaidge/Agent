"""Склейка нескольких mp4 (URL) в один файл через ffmpeg concat."""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import httpx

logger = logging.getLogger(__name__)


class FinalVideoAssemblerError(Exception):
    """Не удалось скачать кадры или выполнить ffmpeg."""


def _download(url: str, dest: Path, timeout_sec: float = 300.0) -> None:
    with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)


def assemble_remote_mp4s(
    video_urls: list[str],
    output_path: Path,
    *,
    temp_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """
    Скачивает каждый URL во временный mp4 и склеивает через ffmpeg demuxer concat.
    """
    if not video_urls:
        raise FinalVideoAssemblerError("Нет URL для склейки")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FinalVideoAssemblerError(
            "ffmpeg не найден в PATH — установите ffmpeg для финальной склейки"
        )

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        logger.info("final_video_assembler: %s", msg)
        if progress:
            progress(msg)

    with tempfile.TemporaryDirectory(dir=temp_dir) as td:
        tdp = Path(td)
        part_paths: list[Path] = []
        for i, url in enumerate(video_urls):
            part = tdp / f"part_{i:03d}.mp4"
            log(f"скачивание {i + 1}/{len(video_urls)}")
            _download(url, part)
            part_paths.append(part)

        list_file = tdp / "list.txt"
        lines = [f"file '{p.as_posix()}'" for p in part_paths]
        list_file.write_text("\n".join(lines), encoding="utf-8")

        log("ffmpeg concat")
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output_path),
        ]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if r.returncode != 0:
            raise FinalVideoAssemblerError(
                f"ffmpeg exit {r.returncode}: {r.stderr[-2000:]!s}"
            )

    log(f"готово: {output_path}")
    return output_path
