"""Запуск cloudflared quick tunnel и извлечение публичного trycloudflare.com URL."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_TUNNEL_URL_RE = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")


def try_extract_trycloudflare_url(line: str) -> str | None:
    """Достаёт публичный host из строки лога cloudflared (для отдельного скрипта туннеля)."""
    m = _TUNNEL_URL_RE.search(line)
    return m.group(0) if m else None


async def wait_for_persisted_tunnel_base_url(
    runtime_file: Path,
    timeout_sec: float,
) -> bool:
    """Ждёт непустой URL в файле (отдельный run_cloudflared_tunnel.py)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    while loop.time() < deadline:
        if read_persisted_tunnel_base_url(runtime_file).strip():
            return True
        await asyncio.sleep(0.35)
    return bool(read_persisted_tunnel_base_url(runtime_file).strip())


def read_persisted_tunnel_base_url(runtime_file: Path) -> str:
    """
    Базовый https URL из data/runtime/current_tunnel.txt (пишет встроенный туннель или run_cloudflared_tunnel.py).
    """
    try:
        if not runtime_file.is_file():
            return ""
        text = runtime_file.read_text(encoding="utf-8")
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            got = try_extract_trycloudflare_url(line)
            if got:
                return got.rstrip("/")
        return ""
    except OSError:
        return ""


_state_lock = threading.Lock()
_current_tunnel_url: str = ""
_tunnel_proc: subprocess.Popen[str] | None = None
_tunnel_thread: threading.Thread | None = None
_url_ready = threading.Event()


def get_current_tunnel_url() -> str:
    """Публичный URL последнего обнаруженного туннеля или пустая строка."""
    with _state_lock:
        return _current_tunnel_url


def _validate_cloudflared_file(path: Path) -> tuple[bool, str]:
    """Проверка: существует, файл, размер > 0. Возвращает (ok, причина или размер в байтах как str)."""
    if not path.exists():
        return False, "файл не существует"
    if not path.is_file():
        return False, "путь не является файлом (возможно каталог)"
    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, f"не удалось прочитать атрибуты: {exc}"
    if size <= 0:
        return False, "размер 0 байт (пустой или фиктивный файл — см. CLOUDFLARED_BIN)"
    return True, str(size)


def resolve_cloudflared_binary(explicit_bin: str | None) -> Path | None:
    """
    Выбор бинарника: приоритет CLOUDFLARED_BIN, иначе shutil.which('cloudflared').
    Каждый кандидат проверяется: существование, файл, размер > 0.

    Если задан явный путь в ENV и он невалиден — None (к PATH не переходим).
    """
    stripped = (explicit_bin or "").strip()
    if stripped:
        raw = Path(stripped).expanduser()
        try:
            resolved = raw.resolve()
        except OSError as exc:
            logger.error(
                "CLOUDFLARED_BIN невалиден: не удалось разрешить путь %s: %s",
                raw,
                exc,
            )
            return None
        ok, detail = _validate_cloudflared_file(resolved)
        if not ok:
            logger.error(
                "CLOUDFLARED_BIN невалиден (%s): %s — туннель не запускается",
                resolved,
                detail,
            )
            return None
        logger.info(
            "Cloudflare tunnel: запуск через явный путь CLOUDFLARED_BIN — %s (размер %s байт)",
            resolved,
            detail,
        )
        return resolved

    which = shutil.which("cloudflared")
    if not which:
        logger.error(
            "cloudflared не найден: задайте CLOUDFLARED_BIN к рабочему cloudflared.exe "
            "или установите клиент в PATH. "
            "Документация: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/"
        )
        return None

    resolved = Path(which).resolve()
    ok, detail = _validate_cloudflared_file(resolved)
    if not ok:
        logger.error(
            "cloudflared из PATH невалиден (%s): %s — задайте CLOUDFLARED_BIN к рабочему бинарнику",
            resolved,
            detail,
        )
        return None
    logger.info(
        "Cloudflare tunnel: бинарник из PATH — %s (размер %s байт)",
        resolved,
        detail,
    )
    return resolved


def _set_tunnel_url(url: str, runtime_file: Path | None) -> None:
    global _current_tunnel_url
    with _state_lock:
        if _current_tunnel_url:
            return
        _current_tunnel_url = url
    _url_ready.set()
    logger.info("Cloudflare tunnel URL detected: %s", url)
    if runtime_file is not None:
        try:
            runtime_file.parent.mkdir(parents=True, exist_ok=True)
            runtime_file.write_text(url + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("Не удалось записать %s: %s", runtime_file, exc)


def _drain_reader(proc: subprocess.Popen[str], runtime_file: Path | None) -> None:
    assert proc.stdout is not None
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            match = _TUNNEL_URL_RE.search(line)
            if match:
                url = match.group(0)
                with _state_lock:
                    already = bool(_current_tunnel_url)
                if not already:
                    _set_tunnel_url(url, runtime_file)
    finally:
        try:
            proc.stdout.close()
        except OSError:
            pass


def _run_tunnel(
    local_url: str,
    runtime_file: Path | None,
    cloudflared_exe: Path,
) -> None:
    global _tunnel_proc, _tunnel_thread
    proc: subprocess.Popen[str] | None = None
    cmd = [str(cloudflared_exe), "tunnel", "--url", local_url]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError as exc:
        logger.error("Не удалось запустить cloudflared (%s): %s", cloudflared_exe, exc)
        with _state_lock:
            _tunnel_thread = None
        return

    with _state_lock:
        _tunnel_proc = proc

    try:
        _drain_reader(proc, runtime_file)
        rc = proc.poll()
        if rc not in (0, None) and rc != -15:  # -15: SIGTERM на Unix
            logger.warning("Процесс cloudflared завершился с кодом %s", rc)
    finally:
        with _state_lock:
            if _tunnel_proc is proc:
                _tunnel_proc = None
            _tunnel_thread = None


def start_cloudflare_tunnel_background(
    local_url: str,
    *,
    runtime_file: Path | None = None,
    cloudflared_bin: str | None = None,
) -> bool:
    """
    Запускает `cloudflared tunnel --url <local_url>` в отдельном потоке, читает stdout.

    Возвращает False, если бинарник не найден / невалиден или туннель уже запущен.
    """
    global _tunnel_thread

    exe = resolve_cloudflared_binary(cloudflared_bin)
    if exe is None:
        return False

    with _state_lock:
        if _tunnel_proc is not None:
            logger.warning("Cloudflare tunnel уже запущен, повторный запуск пропущен")
            return False

    def _reset_start_flags() -> None:
        global _current_tunnel_url
        _url_ready.clear()
        with _state_lock:
            _current_tunnel_url = ""

    _reset_start_flags()

    thread = threading.Thread(
        target=_run_tunnel,
        args=(local_url, runtime_file, exe),
        name="cloudflared-tunnel",
        daemon=True,
    )
    with _state_lock:
        _tunnel_thread = thread
    thread.start()
    return True


async def wait_for_cloudflare_tunnel_url(timeout_sec: float) -> bool:
    """
    Ждёт появления публичного URL в логах cloudflared.

    Раньше использовался только threading.Event — если cloudflared печатает URL позже
    (часто 15–40 с после старта), таймаут 12 с срабатывал раньше строки, и setWebhook
    уходил без туннельного URL. Опрашиваем get_current_tunnel_url() до конца окна.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    while loop.time() < deadline:
        if get_current_tunnel_url().strip():
            return True
        await asyncio.sleep(0.25)
    return bool(get_current_tunnel_url().strip())


def stop_cloudflare_tunnel() -> None:
    """Завершает процесс cloudflared при остановке приложения."""
    global _tunnel_proc, _tunnel_thread

    with _state_lock:
        proc = _tunnel_proc
        thr = _tunnel_thread

    if proc is None:
        return

    try:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    except OSError as exc:
        logger.warning("Ошибка при остановке cloudflared: %s", exc)
    finally:
        with _state_lock:
            _tunnel_proc = None
            _tunnel_thread = None
        if thr is not None and thr.is_alive():
            thr.join(timeout=3)
