"""Локальный веб-просмотр журнала бота: вход по паролю, RAG, system, ответ модели."""
from __future__ import annotations

import hashlib
import html
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for name in ("ENV", "env", ".env"):
    p = ROOT / name
    if p.is_file():
        from dotenv import load_dotenv

        load_dotenv(p, override=True)
        break

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from uvicorn import run

from audit_log import get_turn_by_id, iter_turns

DATA_DIR = Path(os.environ.get("MONITOR_DATA_DIR") or (ROOT / "data"))

SESSION_KEY = "monitor_ok"

MONITOR_CSS = """
:root {
  --bg: #0a0c10;
  --surface: #12151c;
  --surface2: #1a1f2a;
  --border: #2a3140;
  --text: #e8eaed;
  --muted: #8b93a8;
  --accent: #3db4d8;
  --accent-dim: #2a8fa8;
  --user-bg: #1a2333;
  --bot-bg: #152218;
  --warn: #e8a838;
  --radius: 12px;
  --font: "Segoe UI", system-ui, -apple-system, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: var(--font); background: var(--bg); color: var(--text);
  min-height: 100vh; line-height: 1.5;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: 920px; margin: 0 auto; padding: 1.25rem 1.25rem 3rem; }
.topbar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem 1rem;
  margin-bottom: 1.25rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border);
}
.topbar h1 { margin: 0; font-size: 1.2rem; font-weight: 650; letter-spacing: -0.02em; }
.badge {
  display: inline-flex; align-items: center; gap: 0.35rem;
  font-size: 0.75rem; color: var(--muted); background: var(--surface2);
  padding: 0.25rem 0.6rem; border-radius: 999px; border: 1px solid var(--border);
}
.badge-live { color: #6dceb8; border-color: #2a4d42; }
.badge-live::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%; background: #3dd9a8;
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse { 50% { opacity: 0.35; } }
.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
.chip {
  font-size: 0.8rem; padding: 0.2rem 0.55rem; border-radius: 6px;
  background: var(--surface2); border: 1px solid var(--border); color: var(--muted);
}
.chip a { color: var(--accent); }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  margin-bottom: 1rem; overflow: hidden;
  box-shadow: 0 4px 24px rgba(0,0,0,0.25);
}
.card-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.75rem;
  padding: 0.65rem 1rem; background: var(--surface2); border-bottom: 1px solid var(--border);
  font-size: 0.8rem; color: var(--muted);
}
.chat-pill {
  font-weight: 650; color: var(--accent); font-variant-numeric: tabular-nums;
}
.model-tag { font-size: 0.72rem; opacity: 0.9; }
.card-body { padding: 0.9rem 1rem; display: flex; flex-direction: column; gap: 0.85rem; }
.msg-block { border-radius: 8px; padding: 0.65rem 0.85rem; font-size: 0.9rem; }
.msg-block label {
  display: block; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted); margin-bottom: 0.35rem; font-weight: 600;
}
.msg-user { background: var(--user-bg); border-left: 3px solid var(--accent); }
.msg-bot { background: var(--bot-bg); border-left: 3px solid #4caf7a; }
.msg-text {
  white-space: pre-wrap; word-break: break-word; max-height: 14rem; overflow-y: auto;
}
.ctx-row {
  font-size: 0.78rem; color: var(--muted); padding: 0.5rem 0.65rem;
  background: var(--bg); border-radius: 8px; border: 1px dashed var(--border);
}
.ctx-row strong { color: var(--warn); font-weight: 600; }
.detail-link {
  display: inline-block; margin-top: 0.25rem; font-size: 0.82rem; font-weight: 600;
}
.login-card {
  max-width: 400px; margin: 4rem auto; padding: 2rem;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: 0 8px 40px rgba(0,0,0,0.35);
}
.login-card h1 { margin: 0 0 1rem; font-size: 1.35rem; }
.login-card input[type="password"] {
  width: 100%; padding: 0.65rem; margin: 0.35rem 0 1rem; border-radius: 8px;
  border: 1px solid var(--border); background: var(--bg); color: var(--text); font-size: 1rem;
}
.login-card button {
  padding: 0.6rem 1.2rem; border-radius: 8px; border: none;
  background: var(--accent-dim); color: #fff; font-weight: 600; cursor: pointer; font-size: 0.95rem;
}
.login-card button:hover { filter: brightness(1.08); }
.err { color: #f07178; margin-bottom: 0.75rem; font-size: 0.9rem; }
.hint { color: var(--muted); font-size: 0.82rem; margin-top: 1rem; }
.hint code { background: var(--bg); padding: 0.1rem 0.35rem; border-radius: 4px; }
.empty {
  text-align: center; padding: 2.5rem 1rem; color: var(--muted); font-size: 0.95rem;
}
/* детальная страница */
.detail-meta {
  font-size: 0.88rem; color: var(--muted); margin: 0 0 1rem;
}
.panel {
  margin-bottom: 1rem; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--surface); overflow: hidden;
}
.panel h2 {
  margin: 0; padding: 0.55rem 0.9rem; font-size: 0.78rem; font-weight: 650;
  text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted);
  background: var(--surface2); border-bottom: 1px solid var(--border);
}
.panel pre {
  margin: 0; padding: 0.85rem 0.95rem; font-size: 0.82rem; white-space: pre-wrap;
  word-break: break-word; max-height: 28rem; overflow: auto; background: var(--bg);
}
@media (max-width: 560px) {
  .wrap { padding: 1rem; }
  .msg-block .msg-text { max-height: 10rem; }
}
"""


def _monitor_password() -> str | None:
    """Пароль из .env. MONITOR_PASSWORD приоритетнее; MONITOR_SECRET_TOKEN — старый ключ, тот же смысл."""
    p = (os.environ.get("MONITOR_PASSWORD") or "").strip()
    if p:
        return p
    return (os.environ.get("MONITOR_SECRET_TOKEN") or "").strip() or None


def _session_secret() -> str:
    raw = (os.environ.get("MONITOR_SESSION_SECRET") or "").strip()
    if raw:
        return raw if len(raw) >= 32 else (raw * 4)[:32]
    pw = _monitor_password()
    if pw:
        return hashlib.sha256(f"mini-bot-monitor:{pw}".encode()).hexdigest()
    return "insecure-placeholder-change-monitor-password"


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _rag_hint(rag: str) -> str:
    t = (rag or "").strip()
    if not t:
        return "RAG не подмешивался или пусто."
    one = re.sub(r"\s+", " ", t)[:180]
    if len(t) > 180:
        one += "…"
    return one


def _shell(
    title: str,
    body: str,
    *,
    autoreload_sec: int = 0,
) -> str:
    reload_js = ""
    if autoreload_sec > 0:
        reload_js = f"""
    <script>
      (function() {{
        var sec = {autoreload_sec};
        var el = document.getElementById("reload-in");
        function tick() {{
          if (document.hidden) return;
          sec -= 1;
          if (el) el.textContent = sec;
          if (sec <= 0) {{ location.reload(); }}
        }}
        setInterval(tick, 1000);
      }})();
    </script>"""
    return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)}</title>
<style>{MONITOR_CSS}</style>
</head><body>
<div class="wrap">{body}</div>
{reload_js}
</body></html>"""


def _login_page(err: str) -> str:
    msg = f'<div class="err">{_esc(err)}</div>' if err else ""
    inner = f"""
<div class="login-card">
<h1>Монитор бота</h1>
{msg}
<form method="post" action="login"><label>Пароль</label>
<input type="password" name="password" autocomplete="current-password" required/>
<button type="submit">Войти</button></form>
<p class="hint">Переменная <code>MONITOR_PASSWORD</code> в <code>telegram-mini-bot/.env</code></p>
</div>"""
    return _shell("Вход — монитор", inner, autoreload_sec=0)


def _require_session(request: Request) -> None:
    if request.session.get(SESSION_KEY) is True:
        return
    raise HTTPException(status_code=401, detail="login_required")


app = FastAPI(title="Telegram mini-bot monitor", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
    session_cookie="mini_bot_monitor",
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
    https_only=False,
)


@app.get("/login", response_class=HTMLResponse)
async def login_get():
    return HTMLResponse(_login_page(""))


@app.post("/login")
async def login_post(request: Request, password: str = Form(...)):
    expected = _monitor_password()
    if not expected:
        return HTMLResponse(
            _login_page("Задайте MONITOR_PASSWORD в telegram-mini-bot/.env"),
            status_code=200,
        )
    if password.strip() != expected:
        return HTMLResponse(_login_page("Неверный пароль."), status_code=200)
    request.session[SESSION_KEY] = True
    return RedirectResponse(url="..", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="./login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    chat_id: str | None = Query(None),
):
    try:
        _require_session(request)
    except HTTPException:
        return HTMLResponse(_login_page(""), status_code=200)

    turns = list(reversed(iter_turns(DATA_DIR)))
    if chat_id and chat_id.isdigit():
        cid = int(chat_id)
        turns = [t for t in turns if t.get("chat_id") == cid]

    chats = sorted({t.get("chat_id") for t in iter_turns(DATA_DIR) if t.get("chat_id") is not None})

    chat_links_parts = []
    for c in chats[-50:]:
        chat_links_parts.append(f'<span class="chip"><a href="{_esc("?chat_id=" + str(c))}">чат {c}</a></span>')
    chat_links = " ".join(chat_links_parts)

    cards: list[str] = []
    for t in turns[:300]:
        tid = str(t.get("id", ""))
        cid = t.get("chat_id", "")
        ts = str(t.get("ts", ""))
        user_txt = str(t.get("user") or "")
        bot_txt = str(t.get("assistant") or "")
        model = str(t.get("model") or "—")
        rag = str(t.get("rag_context") or "")
        has_sys = bool((t.get("full_system_message") or "").strip())
        rag_note = _rag_hint(rag)
        link = f"turn/{tid}"
        cards.append(
            f"""
<article class="card">
  <div class="card-head">
    <span class="chat-pill">chat_id {_esc(str(cid))}</span>
    <span>{_esc(ts)}</span>
    <span class="model-tag">модель: {_esc(model)}</span>
    <span style="margin-left:auto"><a href="{_esc(link)}">полный ход →</a></span>
  </div>
  <div class="card-body">
    <div class="msg-block msg-user">
      <label>Пользователь (Telegram)</label>
      <div class="msg-text">{_esc(user_txt)}</div>
    </div>
    <div class="msg-block msg-bot">
      <label>Ответ бота</label>
      <div class="msg-text">{_esc(bot_txt)}</div>
    </div>
    <div class="ctx-row">
      <strong>В агента:</strong> в полный запрос входят system + история (если была) + блок RAG + это сообщение.
      Превью RAG: {_esc(rag_note)}
      {" · есть запись полного system в журнале." if has_sys else " · полного system в записи нет (старый формат)."}
    </div>
  </div>
</article>"""
        )

    body_inner = f"""
<header class="topbar">
  <h1>Mini-bot — журнал</h1>
  <span class="badge badge-live">live</span>
  <span class="badge">след. обновление через <span id="reload-in">5</span> с</span>
  <span style="margin-left:auto"><a href="logout">Выйти</a></span>
</header>
<p class="chips">Фильтр: {chat_links or '<span class="chip">нет чатов</span>'} <span class="chip"><a href="./">все</a></span></p>
{"".join(cards) or '<div class="empty">Пока нет ходов — напишите боту в Telegram.</div>'}"""

    return HTMLResponse(content=_shell("Монитор бота", body_inner, autoreload_sec=5))


@app.get("/turn/{turn_id}", response_class=HTMLResponse)
async def turn_detail(request: Request, turn_id: str):
    try:
        _require_session(request)
    except HTTPException:
        return HTMLResponse(_login_page(""), status_code=200)

    t = get_turn_by_id(DATA_DIR, turn_id)
    if not t:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    def panel(title: str, val: str) -> str:
        return f"""<div class="panel"><h2>{_esc(title)}</h2><pre>{_esc(val)}</pre></div>"""

    rag = str(t.get("rag_context") or "")
    if not rag:
        rag = "(пусто — RAG не сработал или отключён)"
    full_sys = str(t.get("full_system_message") or "").strip()
    if not full_sys:
        full_sys = "(нет в записи — старый формат журнала; напиши боту ещё раз после обновления)"
    hist = str(t.get("history_summary") or "").strip()
    if not hist:
        hist = "(диалог пустой или старая запись)"

    quick = f"""
<div class="card" style="margin-bottom:1.25rem">
  <div class="card-head">
    <span class="chat-pill">chat_id {_esc(str(t.get("chat_id")))}</span>
    <span>{_esc(str(t.get("ts","")))}</span>
    <span class="model-tag">модель: {_esc(str(t.get("model","")))}</span>
  </div>
  <div class="card-body">
    <div class="msg-block msg-user">
      <label>Пользователь</label>
      <div class="msg-text">{_esc(str(t.get("user") or ""))}</div>
    </div>
    <div class="msg-block msg-bot">
      <label>Ответ бота</label>
      <div class="msg-text">{_esc(str(t.get("assistant") or ""))}</div>
    </div>
  </div>
</div>"""

    blocks = [
        panel(
            "① Первое system в OpenAI (META + prompt + RAG)",
            "Внизу — «База знаний» и фрагменты из Supabase.\n\n" + full_sys,
        ),
        panel("② История до этого сообщения (усечённо)", hist),
        panel("③ Только фрагменты RAG", rag),
        panel("④ System prompt (файл / override)", str(t.get("system_prompt") or "")),
        panel("⑤ Сообщение пользователя (user после system)", str(t.get("user") or "")),
        panel("⑥ Ответ в Telegram", str(t.get("assistant") or "")),
    ]

    body_inner = f"""
<header class="topbar">
  <h1>Ход {_esc(turn_id[:8])}…</h1>
  <span style="margin-left:auto"><a href="../">← журнал</a> · <a href="../logout">Выйти</a></span>
</header>
<p class="detail-meta">Всё, что ушло в модель, разложено блоками ниже. Сверху — кратко «как в чате».</p>
{quick}
{"".join(blocks)}"""

    return HTMLResponse(content=_shell(f"Ход {turn_id[:8]}…", body_inner, autoreload_sec=0))


def main() -> None:
    host = (os.environ.get("MONITOR_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("MONITOR_PORT") or "8765").strip() or "8765")
    if not _monitor_password():
        print("Внимание: MONITOR_PASSWORD не задан — страница входа покажет подсказку.", file=sys.stderr)
    else:
        print(f"Монитор: http://{host}:{port}/", file=sys.stderr)
    run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
