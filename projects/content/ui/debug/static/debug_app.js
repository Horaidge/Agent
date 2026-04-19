/* global window */
(function () {
  const pollMs = window.__POLL_MS__ || 2500;
  let timer = null;

  const fUser = () => document.getElementById("f_user").value.trim();
  const fChat = () => document.getElementById("f_chat").value.trim();
  const fEtype = () => document.getElementById("f_etype").value.trim();
  const fTrace = () => document.getElementById("f_trace").value.trim();

  function qs() {
    const p = new URLSearchParams();
    const u = fUser();
    const c = fChat();
    const e = fEtype();
    const t = fTrace();
    if (u) p.set("telegram_user_id", u);
    if (c) p.set("telegram_chat_id", c);
    if (e) p.set("event_type", e);
    if (t) p.set("trace_id", t);
    return p.toString();
  }

  async function fetchJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status + " " + (await r.text()));
    return r.json();
  }

  function showDetail(obj) {
    document.getElementById("detail-json").value = JSON.stringify(obj, null, 2);
    switchTab("detail");
  }

  let lastEvents = [];

  function renderEvents(data) {
    const el = document.getElementById("out-events");
    lastEvents = data.events || [];
    const rows = lastEvents.map((ev, i) => {
      const dt = ev.created_at || "";
      return (
        `<div class="ev" data-idx="${i}">` +
        `<span class="tag">${ev.event_type || "?"}</span> ` +
        `<small>${dt}</small> trace=<code>${ev.trace_id || ""}</code><br/>` +
        `<span class="muted">upd=${ev.telegram_update_id ?? "—"} user=${ev.telegram_user_id ?? "—"} chat=${ev.telegram_chat_id ?? "—"}</span>` +
        `</div>`
      );
    });
    el.innerHTML = rows.join("") || "(пусто)";
    el.querySelectorAll(".ev").forEach((node) => {
      node.addEventListener("click", () => {
        const idx = parseInt(node.getAttribute("data-idx"), 10);
        if (!Number.isNaN(idx) && lastEvents[idx]) showDetail(lastEvents[idx]);
      });
    });
  }

  function renderMessages(data) {
    const el = document.getElementById("out-messages");
    el.textContent = JSON.stringify(data.messages || [], null, 2);
  }

  function renderTraces(data) {
    const el = document.getElementById("out-traces");
    el.textContent = (data.trace_ids || []).join("\n") || "(пусто)";
  }

  function renderTelegram(data) {
    document.getElementById("out-telegram").textContent = JSON.stringify(data, null, 2);
  }

  function renderSummary(data) {
    document.getElementById("out-summary").textContent = JSON.stringify(data, null, 2);
  }

  async function loadEvents() {
    const q = qs();
    const url = "/dev/debug/api/events" + (q ? "?" + q : "");
    const data = await fetchJson(url);
    renderEvents(data);
  }

  async function loadMessages() {
    const p = new URLSearchParams();
    const u = fUser();
    const c = fChat();
    if (u) p.set("telegram_user_id", u);
    if (c) p.set("telegram_chat_id", c);
    const url = "/dev/debug/api/messages" + (p.toString() ? "?" + p.toString() : "");
    renderMessages(await fetchJson(url));
  }

  async function loadTraces() {
    renderTraces(await fetchJson("/dev/debug/api/traces"));
  }

  async function loadTelegram() {
    renderTelegram(await fetchJson("/dev/debug/api/telegram/webhook-info"));
  }

  async function loadSummary() {
    renderSummary(await fetchJson("/dev/debug/api/summary"));
  }

  function switchTab(name) {
    document.querySelectorAll(".tabs button").forEach((b) => {
      b.classList.toggle("on", b.dataset.tab === name);
    });
    document.querySelectorAll(".panel").forEach((p) => {
      p.classList.toggle("active", p.id === "panel-" + name);
    });
  }

  document.getElementById("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    const tab = btn.dataset.tab;
    switchTab(tab);
    if (tab === "events") loadEvents().catch(console.error);
    if (tab === "messages") loadMessages().catch(console.error);
    if (tab === "traces") loadTraces().catch(console.error);
    if (tab === "telegram") loadTelegram().catch(console.error);
    if (tab === "summary") loadSummary().catch(console.error);
  });

  document.getElementById("btn_apply").addEventListener("click", () => {
    loadEvents().catch(console.error);
    loadMessages().catch(console.error);
  });

  function tick() {
    const active = document.querySelector(".tabs button.on");
    const tab = active ? active.dataset.tab : "events";
    if (tab === "events") loadEvents().catch(console.error);
    if (tab === "messages") loadMessages().catch(console.error);
    if (tab === "traces") loadTraces().catch(console.error);
    if (tab === "telegram") loadTelegram().catch(console.error);
    if (tab === "summary") loadSummary().catch(console.error);
  }

  loadEvents().catch(console.error);
  timer = setInterval(tick, pollMs);
})();
