(function () {
  var STORAGE_KEY = "dream_dev_gen_history_v1";
  var SEL_MSG_KEY = "dream_dev_selected_message_id";
  var MAX_ITEMS = 15;

  function readHistory() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      var arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr : [];
    } catch (e) {
      return [];
    }
  }

  function writeHistory(items) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch (e) {}
  }

  function renderHistory() {
    var el = document.getElementById("gen-history");
    if (!el) return;
    var items = readHistory();
    if (!items.length) {
      el.innerHTML = '<p class="muted">Пока нет сохранённых генераций в этом браузере.</p>';
      return;
    }
    var html = items
      .map(function (it, idx) {
        var thumbs = (it.urls || [])
          .map(function (u) {
            return (
              '<a href="' +
              escapeAttr(u) +
              '" target="_blank" rel="noopener" class="gen-hist-thumb-wrap"><img src="' +
              escapeAttr(u) +
              '" alt="" loading="lazy" class="gen-hist-thumb"/></a>'
            );
          })
          .join("");
        var t = it.t ? new Date(it.t).toLocaleString() : "";
        return (
          '<article class="gen-hist-card" data-idx="' +
          idx +
          '">' +
          '<div class="gen-hist-thumbs">' +
          thumbs +
          "</div>" +
          '<p class="gen-hist-meta muted">' +
          escapeHtml(t) +
          " · " +
          escapeHtml(it.model || "") +
          " · " +
          escapeHtml(it.size || "") +
          " · " +
          escapeHtml(it.seconds || "") +
          " с</p>" +
          '<p class="gen-hist-prompt">' +
          escapeHtml(it.prompt || "") +
          "</p>" +
          "</article>"
        );
      })
      .join("");
    el.innerHTML = html;
  }

  function escapeHtml(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function escapeAttr(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function pushFromGenResult(container) {
    var card = container && container.querySelector(".gen-card.ok[data-gen-ok='1']");
    if (!card) return;
    var promptEl = card.querySelector(".prompt-preview");
    var prompt = promptEl ? promptEl.textContent.replace(/^Prompt:\s*/i, "").trim() : "";
    var meta = card.querySelector(".gen-meta-line");
    var model = card.getAttribute("data-gen-model") || "";
    var size = card.getAttribute("data-gen-size") || "";
    var seconds = card.getAttribute("data-gen-seconds") || "";
    var imgs = card.querySelectorAll(".gen-preview-img");
    var urls = [];
    imgs.forEach(function (img) {
      if (img.src) urls.push(img.src);
    });
    var entry = {
      t: Date.now(),
      prompt: prompt,
      model: model,
      size: size,
      seconds: seconds,
      urls: urls,
    };
    var list = readHistory().filter(function (x) {
      return (
        x.prompt !== entry.prompt ||
        String(x.urls && x.urls[0]) !== String(entry.urls && entry.urls[0])
      );
    });
    list.unshift(entry);
    if (list.length > MAX_ITEMS) list = list.slice(0, MAX_ITEMS);
    writeHistory(list);
    renderHistory();
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-copy-target]");
    if (!btn) return;
    var id = btn.getAttribute("data-copy-target");
    var node = id ? document.getElementById(id) : null;
    if (!node) return;
    var text = node.textContent || "";
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          var prev = btn.textContent;
          btn.textContent = "Скопировано";
          setTimeout(function () {
            btn.textContent = prev;
          }, 1200);
        },
        function () {}
      );
    }
  });

  function restoreMessageSelection() {
    var id = sessionStorage.getItem(SEL_MSG_KEY);
    if (!id) return;
    document.querySelectorAll(".msg-row").forEach(function (r) {
      r.classList.remove("msg-row--selected");
    });
    var row = document.querySelector('.msg-row[data-msg-id="' + id + '"]');
    if (row) row.classList.add("msg-row--selected");
  }

  document.body.addEventListener("click", function (ev) {
    var tr = ev.target.closest(".msg-row[data-msg-id]");
    if (tr) sessionStorage.setItem(SEL_MSG_KEY, tr.getAttribute("data-msg-id") || "");
  });

  document.body.addEventListener("htmx:afterRequest", function (ev) {
    var xhr = ev.detail && ev.detail.xhr;
    var url = (xhr && xhr.responseURL) || "";
    if (url.indexOf("/dev/api/messages/clear") !== -1 && xhr && xhr.status === 200) {
      try {
        sessionStorage.removeItem(SEL_MSG_KEY);
      } catch (e) {}
    }
  });

  document.body.addEventListener("htmx:afterSwap", function (ev) {
    var d = ev.detail;
    var t = d && (d.target || d.elt);
    if (!t) return;
    if (t.id === "gen-result") pushFromGenResult(t);
    if (t.id === "message-rows") restoreMessageSelection();
    if (t.id === "tools-frame-root") initDevToolsTabs(t);
  });

  function initDevToolsTabs(root) {
    var r = root || document.getElementById("tools-frame-root");
    if (!r) return;
    var strip = r.querySelector(".tools-substrip");
    if (!strip || strip.getAttribute("data-tools-tabs-init") === "1") return;
    strip.setAttribute("data-tools-tabs-init", "1");
    function show(tab) {
      r.querySelectorAll(".tools-tab-btn").forEach(function (b) {
        var on = b.getAttribute("data-tool-tab") === tab;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
      });
      r.querySelectorAll("[data-tool-pane]").forEach(function (p) {
        var on = p.getAttribute("data-tool-pane") === tab;
        p.hidden = !on;
        p.classList.toggle("tools-pane--active", on);
      });
    }
    strip.addEventListener("click", function (ev) {
      var btn = ev.target.closest(".tools-tab-btn[data-tool-tab]");
      if (!btn || !strip.contains(btn)) return;
      show(btn.getAttribute("data-tool-tab") || "registry");
    });
    show("registry");
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderHistory();
    restoreMessageSelection();
    initDevToolsTabs(document.getElementById("tools-frame-root"));
  });
})();
