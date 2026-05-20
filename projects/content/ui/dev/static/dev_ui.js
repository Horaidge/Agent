(function () {
  var STORAGE_KEY = "dream_dev_gen_history_v1";
  var SEL_MSG_KEY = "dream_dev_selected_message_id";
  var STAGE0B_LOCK_KEY = "dream_stage0b_output_locked_v1";
  var STAGE0B_SAVED_JSON_KEY = "dream_stage0b_saved_json_for_stage1_v1";
  var STAGE1_DREAM_TEXT_KEY = "dream_stage1_dream_text_v1";
  var ASSEMBLER_DIRECTOR_JSON_KEY = "dream_assembler_director_input_v1";
  var ASSEMBLER_PIN_KEY = "dream_assembler_director_pin_v1";
  var ASSEMBLER_LOGIC_KEY = "dream_assembler_human_logic_v1";
  var ASSEMBLER_TOOLS_KEY = "dream_assembler_tools_enabled_v1";
  var MAX_ITEMS = 15;
  var videoUploadSwapBound = false;
  var videoJobPanelChangeBound = false;

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
    var armBtn = ev.target.closest("[data-confirm-arm]");
    if (armBtn) {
      var windowMs = parseInt(armBtn.getAttribute("data-confirm-arm-window-ms") || "5000", 10);
      if (!Number.isFinite(windowMs) || windowMs < 1000) windowMs = 5000;
      var msg = armBtn.getAttribute("data-confirm-arm-text") || "Нажмите ещё раз для запуска";
      var armedUntil = parseInt(armBtn.getAttribute("data-armed-until-ms") || "0", 10);
      var now = Date.now();
      if (!armedUntil || now > armedUntil) {
        ev.preventDefault();
        armBtn.setAttribute("data-armed-until-ms", String(now + windowMs));
        var originalText = armBtn.getAttribute("data-original-text") || armBtn.textContent;
        armBtn.setAttribute("data-original-text", originalText);
        armBtn.textContent = msg;
        armBtn.classList.add("btn-warn");
        setTimeout(function () {
          var until2 = parseInt(armBtn.getAttribute("data-armed-until-ms") || "0", 10);
          if (!until2 || Date.now() > until2) {
            armBtn.removeAttribute("data-armed-until-ms");
            armBtn.textContent = armBtn.getAttribute("data-original-text") || originalText;
            armBtn.classList.remove("btn-warn");
          }
        }, windowMs + 50);
        return;
      }
      armBtn.removeAttribute("data-armed-until-ms");
      armBtn.textContent = armBtn.getAttribute("data-original-text") || armBtn.textContent;
      armBtn.classList.remove("btn-warn");
      // второй клик в окне подтверждения пропускаем как обычный submit
    }

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

  function autosizeTextarea(el) {
    if (!el) return;
    el.style.height = "auto";
    var h = Math.min(el.scrollHeight, 420);
    el.style.height = Math.max(h, 96) + "px";
  }

  document.addEventListener("input", function (ev) {
    var ta = ev.target.closest && ev.target.closest("textarea[data-autosize='true']");
    if (ta) autosizeTextarea(ta);
    if (ta && ta.id === "stage0b-beats-json") {
      renderStage0BBeatsPreview();
    }
  });

  document.addEventListener("change", function (ev) {
    var el = ev.target;
    if (!el) return;
    if (el.id === "stage0b-mode") {
      renderStage0BBeatsPreview();
    }
    if (el.id === "stage1-mode") {
      renderStage1ScenaristPreview();
    }
  });

  function initAutosize(root) {
    (root || document).querySelectorAll("textarea[data-autosize='true']").forEach(function (ta) {
      autosizeTextarea(ta);
    });
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderHeaderContextWorld(header, opts) {
    var h = header && typeof header === "object" ? header : {};
    var env = h && h.environment && typeof h.environment === "object" ? h.environment : {};
    var entities = Array.isArray(h.entities) ? h.entities : [];
    var worldProps = Array.isArray(h.world_properties) ? h.world_properties : [];
    var modeLabel = (opts && opts.modeLabel) || "Full JSON";
    var statsLabel = (opts && opts.statsLabel) || "";
    var statsValue = (opts && opts.statsValue) || 0;
    var processingHint = (opts && opts.processingHint) || "";
    var title = (opts && opts.title) || "Header Context";
    var html = "";
    html += '<section class="dream-world-model" aria-label="Header Context">';
    html += '<header class="dream-world-model-head"><h4 class="dream-world-model-title">🌍 ' + esc(title) + "</h4>";
    html += '<div class="dream-world-model-meta">';
    html += '<span class="dream-world-chip">mode: ' + esc(modeLabel) + "</span>";
    html += '<span class="dream-world-chip">' + esc(statsLabel) + ": " + esc(statsValue) + "</span>";
    html += "</div></header>";
    if (processingHint) html += '<p class="muted small dream-world-model-hint">⚙️ ' + esc(processingHint) + "</p>";
    html += '<div class="dream-world-grid">';
    html +=
      '<article class="dream-world-section dream-world-section--summary"><h5>🧭 Summary</h5><p>' +
      esc(h.summary || "—") +
      "</p></article>";
    html +=
      '<article class="dream-world-section dream-world-section--environment"><h5>🏞 Environment</h5><p>' +
      esc(env.world_summary || "—") +
      "</p></article>";
    html += '<article class="dream-world-section dream-world-section--properties"><h5>🧱 World Properties</h5>';
    if (worldProps.length) {
      html += '<div class="dream-world-tags">';
      worldProps.forEach(function (x) {
        html += '<span class="dream-world-tag">' + esc(x) + "</span>";
      });
      html += "</div>";
    } else {
      html += "<p>—</p>";
    }
    html += "</article>";
    html += '<article class="dream-world-section dream-world-section--entities"><h5>🗺 Entities</h5>';
    if (entities.length) {
      html += '<ul class="dream-world-entities">';
      entities.forEach(function (ent, idx) {
        var envId = (ent && ent.env_id) || "env_" + (idx + 1);
        var et = (ent && ent.title) || "—";
        var ed = (ent && ent.description) || "—";
        html += "<li><strong>" + esc(envId) + "</strong> · " + esc(et) + "<br><span>" + esc(ed) + "</span></li>";
      });
      html += "</ul>";
    } else {
      html += "<p>—</p>";
    }
    html += "</article></div></section>";
    return html;
  }

  function renderSceneCardsLikeScenarist(scenes, label) {
    var html = '<div class="pipe-s0-scenes dream-lab-s0-scenes" aria-label="' + esc(label || "Scenes") + '">';
    scenes.forEach(function (s, i) {
      var idx = (s && s.scene_index) || i + 1;
      var beat = s && s.source_beat_index ? " ← Beat " + esc(s.source_beat_index) : "";
      var title = s && s.title ? " · " + esc(s.title) : "";
      var actors = Array.isArray(s && s.actors) && s.actors.length ? s.actors.join(", ") : "—";
      var env = (s && (s.environment || s.environment_requirement)) || "—";
      var mood = (s && s.mood) || "—";
      var goal = (s && s.scene_goal) || "—";
      var state = (s && s.main_character_state) || "—";
      var shortDesc = (s && s.short_description) || "";
      var sceneDesc = (s && s.scene_description) || shortDesc || "—";
      var objs = Array.isArray(s && s.key_objects_or_entities) && s.key_objects_or_entities.length ? s.key_objects_or_entities.join(", ") : "";
      html += '<div class="pipe-s0-scene-card">';
      html += '<div class="pipe-s0-scene-head">Сцена ' + esc(idx) + beat + title + "</div>";
      if (shortDesc) html += '<p class="pipe-s0-field pipe-s0-field--short">' + esc(shortDesc) + "</p>";
      html += '<p class="pipe-s0-field pipe-s0-field--desc">' + esc(sceneDesc) + "</p>";
      html +=
        '<p class="pipe-s0-field pipe-s0-field--actors"><span class="pipe-s0-ico" aria-hidden="true">' +
        (actors.indexOf(",") !== -1 ? "👥" : "👤") +
        "</span> " +
        esc(actors) +
        "</p>";
      html += '<p class="pipe-s0-field pipe-s0-field--env"><span class="pipe-s0-ico" aria-hidden="true">🌍</span> ' + esc(env) + "</p>";
      html += '<p class="pipe-s0-field pipe-s0-field--mood">' + esc(mood) + "</p>";
      html += '<p class="pipe-s0-field pipe-s0-field--meta">scene_goal: ' + esc(goal) + " · main_character_state: " + esc(state) + "</p>";
      if (objs)
        html +=
          '<p class="pipe-s0-field pipe-s0-field--refs"><span class="pipe-s0-ico" aria-hidden="true">🔗</span> ' +
          esc(objs) +
          "</p>";
      html += "</div>";
    });
    html += "</div>";
    return html;
  }

  function renderStage0BBeatsPreview() {
    var src = document.getElementById("stage0b-beats-json");
    var out = document.getElementById("stage0b-beats-preview");
    var modeSel = document.getElementById("stage0b-mode");
    if (!src || !out) return;
    var obj = {};
    try {
      obj = JSON.parse(src.value || "{}");
    } catch (e) {
      out.innerHTML = '<p class="error">Невалидный JSON во входе Beat Planner.</p>';
      return;
    }
    var header = obj && obj.header_context ? obj.header_context : {};
    if (!header || typeof header !== "object") header = {};
    var beats = obj && Array.isArray(obj.beats) ? obj.beats : [];
    var mode = modeSel ? modeSel.value : "full";
    var beatsForPreview = beats;
    var html = "";
    html += renderHeaderContextWorld(header, {
      title: "Header Context · Input от Beat Planner",
      modeLabel: mode === "per_beat" ? "Per-beat" : "Full JSON",
      statsLabel: "beats_total",
      statsValue: beats.length,
      processingHint:
        mode === "per_beat"
          ? "последовательный проход по всем beats (итеративно), без ручного выбора."
          : "",
    });
    if (beatsForPreview.length) {
      html += '<div class="dream-beat-cards" aria-label="Beat input for scenarist">';
      beatsForPreview.forEach(function (b, i) {
        var actors = Array.isArray(b && b.actors) && b.actors.length ? b.actors.join(", ") : "—";
        html += '<article class="dream-beat-card">';
        html += '<header class="dream-beat-card-head"><span class="dream-beat-index">Beat ' + esc((b && b.beat_index) || i + 1) + "</span>";
        html += '<span class="dream-beat-function">' + esc((b && b.story_function) || "—") + "</span></header>";
        html += '<h4 class="dream-beat-title">' + esc((b && b.title) || "—") + "</h4>";
        html += '<p class="dream-beat-line"><span>core_event:</span> ' + esc((b && b.core_event) || "—") + "</p>";
        html += '<p class="dream-beat-desc">' + esc((b && b.beat_description) || "—") + "</p>";
        var steps = Array.isArray(b && b.event_steps) && b.event_steps.length ? b.event_steps.join(" · ") : "—";
        var ents =
          Array.isArray(b && b.key_objects_or_entities) && b.key_objects_or_entities.length
            ? b.key_objects_or_entities.join(", ")
            : "—";
        html += '<p class="dream-beat-line"><span>event_steps:</span> ' + esc(steps) + "</p>";
        html += '<p class="dream-beat-line"><span>actors:</span> ' + esc(actors) + "</p>";
        var envRefs = Array.isArray(b && b.environment_refs) && b.environment_refs.length ? b.environment_refs.join(", ") : "—";
        html += '<p class="dream-beat-line"><span>environment_refs:</span> ' + esc(envRefs) + "</p>";
        html += '<p class="dream-beat-line"><span>environment_focus:</span> ' + esc((b && (b.environment_focus || b.environment)) || "—") + "</p>";
        html += '<p class="dream-beat-line"><span>main_character_state:</span> ' + esc((b && b.main_character_state) || "—") + "</p>";
        html += '<p class="dream-beat-line"><span>key_objects_or_entities:</span> ' + esc(ents) + "</p>";
        html += '<p class="dream-beat-line"><span>transition_out:</span> ' + esc((b && b.transition_out) || "—") + "</p>";
        html += "</article>";
      });
      html += "</div>";
    } else {
      html += '<p class="muted small">beats отсутствуют или пусты.</p>';
    }
    out.innerHTML = html;
  }

  function renderStage1ScenaristPreview() {
    var src = document.getElementById("stage1-scenarist-json");
    var out = document.getElementById("stage1-scenarist-preview");
    var modeSel = document.getElementById("stage1-mode");
    if (!src || !out) return;
    var obj = {};
    try {
      obj = JSON.parse(src.value || "{}");
    } catch (e) {
      out.innerHTML = '<p class="error">Невалидный JSON от Сценариста.</p>';
      var rawErr = document.getElementById("stage1-scenarist-json-raw");
      if (rawErr) {
        rawErr.textContent = String(src.value || "").trim() || "{}";
        rawErr.removeAttribute("data-json-hl-done");
        initDreamJsonHighlights(document);
      }
      return;
    }
    var mode = modeSel ? modeSel.value : "full";
    var header = obj && obj.header_context ? obj.header_context : {};
    if (!header || typeof header !== "object") header = {};
    var scenes = obj && Array.isArray(obj.scenes) ? obj.scenes : [];
    var html = "";
    html += renderHeaderContextWorld(header, {
      title: "Header Context · Input от Сценариста",
      modeLabel: mode === "per_scene" ? "Per-scene" : "Full JSON",
      statsLabel: "scenes_total",
      statsValue: scenes.length,
      processingHint:
        mode === "per_scene"
          ? "последовательный проход по всем scenes (итеративно), без ручного выбора."
          : "",
    });
    if (scenes.length) {
      html += renderSceneCardsLikeScenarist(scenes, "Scenes input for director");
    } else {
      html += '<p class="muted small">Сцены отсутствуют или пусты.</p>';
    }
    out.innerHTML = html;
    var rawPre = document.getElementById("stage1-scenarist-json-raw");
    if (rawPre) {
      var pretty = "";
      try {
        pretty = JSON.stringify(obj, null, 2);
      } catch (e2) {
        pretty = String(src.value || "");
      }
      rawPre.textContent = pretty;
      rawPre.removeAttribute("data-json-hl-done");
      initDreamJsonHighlights(document);
    }
  }

  function initDirectorPreflight(root) {
    var scope = root || document;
    var finalNode = scope.querySelector("#stage1-final-copy");
    var listHost = scope.querySelector("#director-preflight-scene-list");
    var textPre = scope.querySelector("#director-preflight-text-json");
    var imagePre = scope.querySelector("#director-preflight-image-json");
    var videoPre = scope.querySelector("#director-preflight-video-json");
    var allPre = scope.querySelector("#director-preflight-all-json");
    if (!finalNode || !listHost || !textPre || !imagePre || !videoPre || !allPre) return;

    var parsed = {};
    try {
      parsed = JSON.parse((finalNode.textContent || "").trim() || "{}");
    } catch (e) {
      textPre.textContent = "{}";
      imagePre.textContent = "{}";
      videoPre.textContent = "{}";
      allPre.textContent = "{}";
      return;
    }
    var header = parsed && parsed.header_context && typeof parsed.header_context === "object" ? parsed.header_context : {};
    var kfItems =
      parsed &&
      parsed.key_frames &&
      Array.isArray(parsed.key_frames.items) &&
      parsed.key_frames.items.length
        ? parsed.key_frames.items
        : [];
    var scenes =
      kfItems.length > 0
        ? kfItems.map(function (kf) {
            var fi = (kf && kf.frame_index) || 0;
            return {
              scene_index: fi,
              source_beat_index: Array.isArray(kf.source_scene_indices) && kf.source_scene_indices.length
                ? kf.source_scene_indices[0]
                : null,
              title: (kf && kf.short_label) || "Кадр " + fi,
              scene_moment: (kf && kf.moment_description) || "",
              actors: Array.isArray(kf.subjects_in_frame) ? kf.subjects_in_frame : [],
              visual_focus: (kf && kf.visual_focus) || "",
              what_to_generate: (kf && kf.image_prompt) || "",
              overlap: String(kf.scene_boundary || "") === "continues_previous",
              dependency_scene_index: kf.continues_from_frame_index != null ? kf.continues_from_frame_index : null,
              generation_strategy:
                String(kf.scene_boundary || "") === "continues_previous"
                  ? "continue_from_previous"
                  : "new_start",
              motion_intensity: "light",
              trim_sec: 0,
              references: Array.isArray(kf.uses_reference_ids)
                ? kf.uses_reference_ids.map(function (rid) {
                    return { kind: "planned_reference", source: String(rid), note: "" };
                  })
                : [],
              visual_prompt: (kf && kf.moment_description) || "",
              image_prompt: (kf && kf.image_prompt) || "",
              animation_prompt: (kf && kf.video_bridge_prompt) || "",
            };
          })
        : parsed && Array.isArray(parsed.final_scenes)
          ? parsed.final_scenes
          : [];

    listHost.innerHTML = scenes
      .map(function (s, i) {
        var idx = (s && s.scene_index) || i + 1;
        var title = (s && s.title) || "—";
        return (
          '<label class="muted small" style="display:flex;align-items:center;gap:0.4rem;">' +
          '<input type="checkbox" class="director-preflight-scene-toggle" data-scene-index="' +
          esc(idx) +
          '" checked> 🎬 Scene ' +
          esc(idx) +
          " · " +
          esc(title) +
          "</label>"
        );
      })
      .join("");

    function selectedSceneIndexes() {
      var selected = [];
      scope.querySelectorAll(".director-preflight-scene-toggle:checked").forEach(function (el) {
        var raw = el.getAttribute("data-scene-index") || "";
        var n = parseInt(raw, 10);
        if (!Number.isNaN(n)) selected.push(n);
      });
      return selected;
    }

    function renderPayloads() {
      var selected = selectedSceneIndexes();
      var selectedRows = scenes.filter(function (row) {
        var idx = parseInt(String((row && row.scene_index) || 0), 10);
        return selected.indexOf(idx) !== -1;
      });

      var textPayload = {
        header_context: header,
        final_scenes: selectedRows.map(function (r) {
          return {
            scene_index: r.scene_index,
            source_beat_index: r.source_beat_index,
            title: r.title,
            scene_moment: r.scene_moment || "",
            actors: Array.isArray(r.actors) ? r.actors : [],
            visual_focus: r.visual_focus || "",
            what_to_generate: r.what_to_generate || "",
            overlap: !!r.overlap,
            dependency_scene_index: r.dependency_scene_index || null,
            generation_strategy: r.generation_strategy || "new_start",
            motion_intensity: r.motion_intensity || "light",
            trim_sec: Number(r.trim_sec || 0),
            references: Array.isArray(r.references) ? r.references : [],
            visual_prompt: r.visual_prompt || "",
            image_prompt: r.image_prompt || "",
            animation_prompt: r.animation_prompt || "",
          };
        }),
      };
      var imagePayload = {
        requests: selectedRows.map(function (r) {
          return {
            scene_index: r.scene_index,
            prompt: r.image_prompt || r.visual_prompt || "",
            reference_source: r.reference_source || "none",
            reference_type: r.reference_type || "none",
            reference_image_url: r.reference_image_url || "",
          };
        }),
      };
      var videoPayload = {
        requests: selectedRows.map(function (r) {
          return {
            scene_index: r.scene_index,
            prompt: r.animation_prompt || "",
            overlap: !!r.overlap,
            dependency_scene_index: r.dependency_scene_index || null,
            trim_start_sec: Number(r.trim_sec || 0),
            last_frame_reference: !!r.overlap,
          };
        }),
      };
      var bundlePayload = {
        mode: "manual_preflight",
        text_plan: textPayload,
        image_payload: imagePayload,
        video_payload: videoPayload,
      };

      textPre.textContent = JSON.stringify(textPayload, null, 2);
      imagePre.textContent = JSON.stringify(imagePayload, null, 2);
      videoPre.textContent = JSON.stringify(videoPayload, null, 2);
      allPre.textContent = JSON.stringify(bundlePayload, null, 2);

      var tc = scope.querySelector("#director-preflight-text-count");
      var ic = scope.querySelector("#director-preflight-image-count");
      var vc = scope.querySelector("#director-preflight-video-count");
      if (tc) tc.textContent = String(selectedRows.length);
      if (ic) ic.textContent = String(imagePayload.requests.length);
      if (vc) vc.textContent = String(videoPayload.requests.length);
    }

    if (!listHost.getAttribute("data-preflight-bound")) {
      listHost.setAttribute("data-preflight-bound", "1");
      listHost.addEventListener("change", function (ev) {
        var t = ev.target;
        if (t && t.classList && t.classList.contains("director-preflight-scene-toggle")) {
          renderPayloads();
        }
      });
    }
    renderPayloads();
  }

  function initDirectorFocusAccordion(root) {
    var scope = root || document;
    var list = scope.querySelectorAll(".director-workbench");
    list.forEach(function (workbench) {
      if (!workbench || workbench.getAttribute("data-focus-init") === "1") return;
      workbench.setAttribute("data-focus-init", "1");
      var inputPanel = workbench.querySelector(".director-input-panel");
      var outputPanel = workbench.querySelector(".director-output-panel");
      function setFocus(mode) {
        if (mode !== "input" && mode !== "output") return;
        workbench.setAttribute("data-focus", mode);
      }
      if (inputPanel) {
        inputPanel.addEventListener("click", function () {
          setFocus("input");
        });
        inputPanel.addEventListener("focusin", function () {
          setFocus("input");
        });
      }
      if (outputPanel) {
        outputPanel.addEventListener("click", function () {
          setFocus("output");
        });
        outputPanel.addEventListener("focusin", function () {
          setFocus("output");
        });
      }
      workbench.querySelectorAll("[data-director-focus]").forEach(function (btn) {
        if (btn.getAttribute("data-director-focus-bound") === "1") return;
        btn.setAttribute("data-director-focus-bound", "1");
        btn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          setFocus(btn.getAttribute("data-director-focus") || "input");
        });
      });
    });
  }

  /** Аккордеон карточек промптов режиссёра (1A / 1B): одна раскрыта, остальные компактны. */
  function initDirectorPromptCards(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-director-prompt-acc]").forEach(function (acc) {
      if (acc.getAttribute("data-director-prompt-init") === "1") return;
      acc.setAttribute("data-director-prompt-init", "1");
      var cards = acc.querySelectorAll("[data-director-prompt-card]");
      function setExpanded(article, open) {
        if (!article) return;
        article.setAttribute("data-expanded", open ? "1" : "0");
        var hit = article.querySelector(".director-prompt-card-hit");
        if (hit) hit.setAttribute("aria-expanded", open ? "true" : "false");
      }
      function collapseAll() {
        cards.forEach(function (c) {
          setExpanded(c, false);
        });
      }
      cards.forEach(function (card) {
        var hit = card.querySelector(".director-prompt-card-hit");
        if (!hit || hit.getAttribute("data-director-prompt-hit-bound") === "1") return;
        hit.setAttribute("data-director-prompt-hit-bound", "1");
        hit.addEventListener("click", function (ev) {
          ev.preventDefault();
          var isOpen = card.getAttribute("data-expanded") === "1";
          collapseAll();
          setExpanded(card, !isOpen);
        });
      });
    });
  }

  var GREF_IMG_STORAGE = "dreamGrefImg:";

  function persistGlobalRefImagesFromContainer(node) {
    if (!node || !node.querySelectorAll) return;
    node.querySelectorAll("[data-gref-card]").forEach(function (card) {
      var rid = card.getAttribute("data-gref-card");
      if (!rid) return;
      var img = card.querySelector(".director-gref-card__visual img.director-gref-thumb");
      if (img && img.src) {
        try {
          localStorage.setItem(GREF_IMG_STORAGE + rid, img.src);
        } catch (e) {}
      }
    });
  }

  function hydrateGlobalRefImages(container) {
    var scope = container || document;
    if (!scope.querySelectorAll) return;
    scope.querySelectorAll("[data-gref-card]").forEach(function (card) {
      var rid = card.getAttribute("data-gref-card");
      if (!rid) return;
      var vis = card.querySelector(".director-gref-card__visual");
      if (!vis || vis.querySelector("img.director-gref-thumb")) return;
      var u;
      try {
        u = localStorage.getItem(GREF_IMG_STORAGE + rid);
      } catch (e) {}
      if (!u) return;
      var wrap = document.createElement("div");
      wrap.className = "director-gref-visual-media";
      var im = document.createElement("img");
      im.src = u;
      im.className = "director-gref-thumb";
      im.alt = "";
      im.loading = "lazy";
      im.referrerPolicy = "no-referrer";
      wrap.appendChild(im);
      vis.insertBefore(wrap, vis.firstChild);
      var cap = document.createElement("p");
      cap.className = "muted small director-gref-gen-caption";
      cap.textContent = "Восстановлено из кэша браузера (Playground).";
      vis.insertBefore(cap, wrap.nextSibling);
    });
  }

  function onGlobalRefVisualSwapped(target) {
    if (!target || !target.id || String(target.id).indexOf("gref-v-") !== 0) return;
    var img = target.querySelector("img.director-gref-thumb");
    var card = target.closest("[data-gref-card]");
    if (!img || !img.src || !card) return;
    var rid = card.getAttribute("data-gref-card");
    if (!rid) return;
    try {
      localStorage.setItem(GREF_IMG_STORAGE + rid, img.src);
    } catch (e) {}
  }

  function dreamJsonHighlightString(jsonStr) {
    var s = String(jsonStr || "").trim();
    if (!s) return "";
    try {
      s = JSON.stringify(JSON.parse(s), null, 2);
    } catch (e0) {
      /* оставляем исходный текст */
    }
    var escaped = s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return escaped.replace(
      /("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)/g,
      function (match) {
        var cls = "json-number";
        if (/^"/.test(match)) {
          cls = /:$/.test(match) ? "json-key" : "json-string";
        } else if (/true|false/.test(match)) {
          cls = "json-boolean";
        } else if (/null/.test(match)) {
          cls = "json-null";
        }
        return '<span class="' + cls + '">' + match + "</span>";
      }
    );
  }

  function initDreamJsonHighlights(root) {
    var scope = root || document;
    if (!scope || !scope.querySelectorAll) return;
    scope.querySelectorAll("pre[data-json-hl='true']").forEach(function (pre) {
      if (pre.getAttribute("data-json-hl-done") === "1") return;
      var raw = pre.textContent || "";
      if (!raw.trim()) {
        pre.setAttribute("data-json-hl-done", "1");
        return;
      }
      pre.innerHTML = dreamJsonHighlightString(raw);
      pre.setAttribute("data-json-hl-done", "1");
    });
  }

  function setStage0BHint(msg, isError) {
    var hints = document.querySelectorAll("[data-stage0b-save-hint]");
    if (!hints.length) return;
    hints.forEach(function (hint) {
      hint.textContent = msg || "";
      hint.classList.toggle("error", !!isError);
    });
    if (msg) {
      setTimeout(function () {
        hints.forEach(function (hint) {
          if (hint.textContent === msg) hint.textContent = "";
        });
      }, 1800);
    }
  }

  function isScenaristOutputLocked() {
    var pin = document.querySelector("[data-scenarist-output-pin]");
    return !!(pin && pin.checked);
  }

  function bindAllScenaristOutputPins() {
    document.querySelectorAll("[data-scenarist-output-pin]").forEach(function (cb) {
      if (cb.getAttribute("data-scenarist-output-pin-bound") === "1") return;
      cb.setAttribute("data-scenarist-output-pin-bound", "1");
      cb.addEventListener("change", function () {
        var on = cb.checked;
        document.querySelectorAll("[data-scenarist-output-pin]").forEach(function (o) {
          o.checked = on;
        });
        try {
          localStorage.setItem(STAGE0B_LOCK_KEY, on ? "1" : "0");
        } catch (e) {}
      });
    });
  }

  function saveCurrentStage0BToDirectorInput(lockAfterSave) {
    var result = document.getElementById("dream-stage0b-test-result");
    var json0b = result && result.querySelector("#stage0b-final-copy");
    var inp1 = document.getElementById("stage1-scenarist-json");
    if (!json0b || !inp1) {
      setStage0BHint("Нет output для сохранения", true);
      return false;
    }
    var payload = (json0b.textContent || "").trim();
    if (!payload) {
      setStage0BHint("Пустой output Сценариста", true);
      return false;
    }
    inp1.value = payload;
    try {
      localStorage.setItem(STAGE0B_SAVED_JSON_KEY, payload);
    } catch (e) {}
    if (lockAfterSave) {
      document.querySelectorAll("[data-scenarist-output-pin]").forEach(function (x) {
        x.checked = true;
      });
      try {
        localStorage.setItem(STAGE0B_LOCK_KEY, "1");
      } catch (e) {}
    }
    renderStage1ScenaristPreview();
    setStage0BHint("Сохранено для Режиссёра", false);
    return true;
  }

  function getDirectorFinalJsonText() {
    var res = document.getElementById("dream-stage1-test-result");
    var pre = res && res.querySelector("#stage1-final-copy");
    return pre ? (pre.textContent || "").trim() : "";
  }

  function pushDirectorOutputToAssembler(force) {
    var ta = document.getElementById("assembler-director-json");
    if (!ta) return;
    var pin = document.getElementById("assembler-pin-director-input");
    if (pin && pin.checked && !force) return;
    var txt = getDirectorFinalJsonText();
    if (!txt) return;
    ta.value = txt;
    try {
      localStorage.setItem(ASSEMBLER_DIRECTOR_JSON_KEY, txt);
    } catch (e) {}
  }

  function saveAssemblerToolMap() {
    var map = {};
    document.querySelectorAll(".assembler-tool-cb").forEach(function (cb) {
      var name = cb.getAttribute("data-assembler-tool");
      if (name) map[name] = cb.checked;
    });
    try {
      localStorage.setItem(ASSEMBLER_TOOLS_KEY, JSON.stringify(map));
    } catch (e) {}
  }

  function restoreAssemblerToolCheckboxes() {
    var map = {};
    try {
      var raw = localStorage.getItem(ASSEMBLER_TOOLS_KEY);
      if (raw) map = JSON.parse(raw) || {};
    } catch (e) {}
    document.querySelectorAll(".assembler-tool-cb").forEach(function (cb) {
      var name = cb.getAttribute("data-assembler-tool");
      if (!name) return;
      if (Object.prototype.hasOwnProperty.call(map, name)) {
        cb.checked = !!map[name];
      }
      if (cb.getAttribute("data-assembler-tool-bound") === "1") return;
      cb.setAttribute("data-assembler-tool-bound", "1");
      cb.addEventListener("change", saveAssemblerToolMap);
    });
  }

  function initPlaygroundAccordion(root) {
    var acc = root && root.querySelector ? root.querySelector("[data-playground-accordion]") : null;
    if (!acc) acc = document.querySelector("[data-playground-accordion]");
    if (!acc || acc.getAttribute("data-pg-acc-init") === "1") return;
    acc.setAttribute("data-pg-acc-init", "1");
    function expand(item) {
      acc.querySelectorAll(".playground-acc-item").forEach(function (it) {
        var on = it === item;
        it.classList.toggle("is-expanded", on);
        var body = it.querySelector(".playground-acc-body");
        var tr = it.querySelector(".playground-acc-trigger");
        if (body) body.hidden = !on;
        if (tr) tr.setAttribute("aria-expanded", on ? "true" : "false");
      });
    }
    function collapseItem(item) {
      item.classList.remove("is-expanded");
      var body = item.querySelector(".playground-acc-body");
      var tr = item.querySelector(".playground-acc-trigger");
      if (body) body.hidden = true;
      if (tr) tr.setAttribute("aria-expanded", "false");
    }
    acc.querySelectorAll(".playground-acc-item").forEach(function (item) {
      var tr = item.querySelector(".playground-acc-trigger");
      if (!tr) return;
      tr.addEventListener("click", function () {
        if (item.classList.contains("is-expanded")) {
          collapseItem(item);
          return;
        }
        expand(item);
      });
    });
  }

  function isImageFile(f) {
    return !!(f && f.type && f.type.indexOf("image/") === 0);
  }

  /** Drag-and-drop + превью + автоматическая отправка формы загрузки кадра (без отдельной кнопки). */
  function initVideoUploadDropzones(scope) {
    var root = scope && scope.querySelector ? scope : document;
    root.querySelectorAll('form[data-video-auto-upload="1"]').forEach(function (form) {
      if (form.getAttribute("data-video-dz-init") === "1") return;
      form.setAttribute("data-video-dz-init", "1");
      var zone = form.querySelector("[data-video-drop-zone]");
      var input = form.querySelector('input[type="file"][name="file"]');
      var preview = form.querySelector(".video-drop-preview");
      if (!zone || !input || !preview) return;

      var previewUrl = null;
      function revokePreview() {
        if (previewUrl) {
          try {
            URL.revokeObjectURL(previewUrl);
          } catch (e) {}
          previewUrl = null;
        }
      }
      function showPreviewForFile(file) {
        revokePreview();
        if (!file || !isImageFile(file)) {
          preview.hidden = true;
          preview.removeAttribute("src");
          return;
        }
        previewUrl = URL.createObjectURL(file);
        preview.src = previewUrl;
        preview.hidden = false;
      }
      function submitUpload() {
        if (form.getAttribute("data-video-uploading") === "1") return;
        if (!input.files || !input.files.length) return;
        if (!isImageFile(input.files[0])) return;
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          var tmp = document.createElement("button");
          tmp.type = "submit";
          tmp.setAttribute("aria-hidden", "true");
          tmp.style.cssText = "position:absolute;width:0;height:0;opacity:0;pointer-events:none";
          form.appendChild(tmp);
          tmp.click();
          form.removeChild(tmp);
        }
      }
      function setInputFilesFromDrop(file) {
        if (!file || !isImageFile(file)) return false;
        try {
          var dt = new DataTransfer();
          dt.items.add(file);
          input.files = dt.files;
        } catch (e) {
          return false;
        }
        showPreviewForFile(file);
        submitUpload();
        return true;
      }

      input.addEventListener("change", function () {
        var f = input.files && input.files[0];
        showPreviewForFile(f);
        submitUpload();
      });

      ["dragenter", "dragover"].forEach(function (evn) {
        zone.addEventListener(evn, function (e) {
          e.preventDefault();
          e.stopPropagation();
          zone.classList.add("is-dragover");
        });
      });
      zone.addEventListener("dragleave", function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!zone.contains(e.relatedTarget)) zone.classList.remove("is-dragover");
      });
      zone.addEventListener("drop", function (e) {
        e.preventDefault();
        e.stopPropagation();
        zone.classList.remove("is-dragover");
        var fl = e.dataTransfer && e.dataTransfer.files;
        if (!fl || !fl.length) return;
        setInputFilesFromDrop(fl[0]);
      });

      form.addEventListener("htmx:beforeRequest", function () {
        form.setAttribute("data-video-uploading", "1");
        zone.classList.add("is-uploading");
      });
      form.addEventListener("htmx:afterRequest", function () {
        form.removeAttribute("data-video-uploading");
        zone.classList.remove("is-uploading");
      });
    });
  }

  function initVideoJobPanel(root) {
    var scope = root && root.querySelector ? root : document;
    initVideoUploadDropzones(scope);
    var form = scope.querySelector ? scope.querySelector("#form-video-job") : document.getElementById("form-video-job");
    if (!form || form.getAttribute("data-video-panel-init") === "1") return;
    form.setAttribute("data-video-panel-init", "1");
    var modeHidden = document.getElementById("video-source-mode");
    var uploadPanel = document.getElementById("video-first-upload-panel");
    var libPanel = document.getElementById("video-first-library-panel");
    var btns = document.querySelectorAll("[data-video-first-mode]");
    function setMode(isLibrary) {
      if (modeHidden) modeHidden.value = isLibrary ? "dream_asset" : "upload";
      if (uploadPanel) uploadPanel.hidden = !!isLibrary;
      if (libPanel) libPanel.hidden = !isLibrary;
      btns.forEach(function (b) {
        var lib = b.getAttribute("data-video-first-mode") === "library";
        b.classList.toggle("is-active", lib === !!isLibrary);
        b.setAttribute("aria-pressed", lib === !!isLibrary ? "true" : "false");
      });
    }
    btns.forEach(function (b) {
      b.addEventListener("click", function (ev) {
        ev.preventDefault();
        var lib = b.getAttribute("data-video-first-mode") === "library";
        setMode(lib);
      });
    });
    if (!videoJobPanelChangeBound) {
      videoJobPanelChangeBound = true;
      document.body.addEventListener("change", function (ev) {
        var t = ev.target;
        if (!t || !t.matches || t.name !== "dream_asset_id") return;
        if (!t.closest("#video-first-library-panel")) return;
        var mh = document.getElementById("video-source-mode");
        if (mh) mh.value = "dream_asset";
      });
    }
    if (!videoUploadSwapBound) {
      videoUploadSwapBound = true;
      document.body.addEventListener("htmx:afterSwap", function (ev) {
        var d = ev.detail;
        var elt = d && d.target;
        if (!elt) return;
        if (elt.id === "video-first-frame-upload-slot") {
          var mh = document.getElementById("video-source-mode");
          if (mh) mh.value = "upload";
          var up = document.getElementById("video-first-upload-panel");
          var lp = document.getElementById("video-first-library-panel");
          var allBtns = document.querySelectorAll("[data-video-first-mode]");
          if (up) up.hidden = false;
          if (lp) lp.hidden = true;
          allBtns.forEach(function (b) {
            var lib = b.getAttribute("data-video-first-mode") === "library";
            b.classList.toggle("is-active", !lib);
            b.setAttribute("aria-pressed", !lib ? "true" : "false");
          });
        }
      });
    }
    var backendSel = document.getElementById("video-backend-select");
    var dsw = document.getElementById("video-dashscope-model-wrap");
    var orw = document.getElementById("video-openrouter-wrap");
    function syncVideoBackendUi() {
      if (!backendSel || !dsw || !orw) return;
      var isOr = backendSel.value === "openrouter";
      dsw.hidden = isOr;
      orw.hidden = !isOr;
    }
    if (backendSel && !backendSel.getAttribute("data-video-backend-bound")) {
      backendSel.setAttribute("data-video-backend-bound", "1");
      backendSel.addEventListener("change", syncVideoBackendUi);
    }
    syncVideoBackendUi();
    setMode(false);
  }

  function restoreAssemblerWorkbench() {
    var ta = document.getElementById("assembler-director-json");
    var pin = document.getElementById("assembler-pin-director-input");
    var logic = document.getElementById("assembler-human-logic");
    if (pin) {
      try {
        pin.checked = localStorage.getItem(ASSEMBLER_PIN_KEY) === "1";
      } catch (e) {}
      if (!pin.getAttribute("data-assembler-pin-bound")) {
        pin.setAttribute("data-assembler-pin-bound", "1");
        pin.addEventListener("change", function () {
          try {
            localStorage.setItem(ASSEMBLER_PIN_KEY, pin.checked ? "1" : "0");
          } catch (e) {}
        });
      }
    }
    if (ta) {
      try {
        var s = localStorage.getItem(ASSEMBLER_DIRECTOR_JSON_KEY);
        if (s && s.trim()) ta.value = s;
      } catch (e) {}
      if (!ta.getAttribute("data-assembler-director-bound")) {
        ta.setAttribute("data-assembler-director-bound", "1");
        ta.addEventListener("change", function () {
          try {
            localStorage.setItem(ASSEMBLER_DIRECTOR_JSON_KEY, ta.value || "");
          } catch (e) {}
        });
      }
    }
    if (logic) {
      try {
        var lg = localStorage.getItem(ASSEMBLER_LOGIC_KEY);
        if (lg) logic.value = lg;
      } catch (e) {}
      if (!logic.getAttribute("data-assembler-logic-bound")) {
        logic.setAttribute("data-assembler-logic-bound", "1");
        logic.addEventListener("change", function () {
          try {
            localStorage.setItem(ASSEMBLER_LOGIC_KEY, logic.value || "");
          } catch (e) {}
        });
      }
    }
    restoreAssemblerToolCheckboxes();
    var asmForm = document.getElementById("assembler-sandbox-form");
    if (asmForm && !asmForm.getAttribute("data-assembler-submit-bound")) {
      asmForm.setAttribute("data-assembler-submit-bound", "1");
      asmForm.addEventListener("submit", function () {
        var names = [];
        asmForm.querySelectorAll(".assembler-tool-cb:checked").forEach(function (cb) {
          var n = cb.getAttribute("data-assembler-tool");
          if (n) names.push(n);
        });
        var hid = document.getElementById("assembler-enabled-tools-json");
        if (hid) hid.value = JSON.stringify(names);
      });
    }
  }

  function restoreStage1DreamText() {
    var ta = document.getElementById("stage1-dream-text");
    if (!ta) return;
    try {
      var s = localStorage.getItem(STAGE1_DREAM_TEXT_KEY);
      if (s != null && s !== "") ta.value = s;
    } catch (e) {}
    if (!ta.getAttribute("data-stage1-dream-bound")) {
      ta.setAttribute("data-stage1-dream-bound", "1");
      ta.addEventListener("input", function () {
        try {
          localStorage.setItem(STAGE1_DREAM_TEXT_KEY, ta.value || "");
        } catch (e) {}
      });
      ta.addEventListener("change", function () {
        try {
          localStorage.setItem(STAGE1_DREAM_TEXT_KEY, ta.value || "");
        } catch (e) {}
      });
    }
  }

  function syncDreamTextFromBeatPlanner() {
    var d0 = document.getElementById("stage0a-dream-text");
    var d1 = document.getElementById("stage1-dream-text");
    if (!d0 || !d1) return;
    var v = (d0.value || "").trim();
    if (!v) return;
    d1.value = d0.value;
    try {
      localStorage.setItem(STAGE1_DREAM_TEXT_KEY, d1.value || "");
    } catch (e) {}
  }

  function restoreStage0BDirectorState() {
    var locked = false;
    try {
      locked = localStorage.getItem(STAGE0B_LOCK_KEY) === "1";
    } catch (e) {}
    document.querySelectorAll("[data-scenarist-output-pin]").forEach(function (cb) {
      cb.checked = locked;
    });
    bindAllScenaristOutputPins();
    restoreStage1DreamText();
    var inp1 = document.getElementById("stage1-scenarist-json");
    if (inp1) {
      try {
        var saved = localStorage.getItem(STAGE0B_SAVED_JSON_KEY);
        if (saved && saved.trim()) {
          inp1.value = saved;
          renderStage1ScenaristPreview();
        }
      } catch (e) {}
    }
  }

  document.body.addEventListener("htmx:beforeRequest", function (ev) {
    var form = ev.detail && ev.detail.elt;
    if (form && form.classList && form.classList.contains("dream-decomp-form")) {
      var saveBtn = form.querySelector("button[type='submit']");
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.setAttribute("data-prev-label", saveBtn.textContent || "Сохранить");
        saveBtn.textContent = "Сохранение...";
      }
    }
    if (!form || !form.classList || !form.classList.contains("dream-sandbox-form")) return;
    form.classList.add("is-running");
    form.querySelectorAll(".dream-sandbox-run").forEach(function (b) {
      b.disabled = true;
    });
    var status = form.querySelector(".dream-sandbox-status");
    if (status) {
      status.classList.add("is-running");
      status.textContent = status.getAttribute("data-running-text") || "Выполняется...";
    }
  });

  function finishSandboxState(form, ok, xhr) {
    if (!form || !form.classList || !form.classList.contains("dream-sandbox-form")) return;
    form.classList.remove("is-running");
    form.querySelectorAll(".dream-sandbox-run").forEach(function (b) {
      b.disabled = false;
    });
    var status = form.querySelector(".dream-sandbox-status");
    if (status) {
      status.classList.remove("is-running");
      if (ok) {
        status.textContent = "Готово";
      } else {
        var hint = "Ошибка запуска";
        if (xhr && typeof xhr.status === "number" && xhr.status > 0) {
          hint += " (HTTP " + xhr.status + ")";
        }
        if (xhr && xhr.responseText) {
          var body = String(xhr.responseText)
            .replace(/<script[\s\S]*?<\/script>/gi, " ")
            .replace(/<[^>]+>/g, " ")
            .replace(/\s+/g, " ")
            .trim();
          if (body) hint += ": " + body.slice(0, 200);
        }
        status.textContent = hint;
      }
    }
  }

  document.body.addEventListener("htmx:afterRequest", function (ev) {
    var form = ev.detail && ev.detail.elt;
    if (form && form.classList && form.classList.contains("dream-decomp-form")) {
      var xhrSave = ev.detail && ev.detail.xhr;
      var okSave = !!(xhrSave && xhrSave.status >= 200 && xhrSave.status < 300);
      var saveBtn = form.querySelector("button[type='submit']");
      if (saveBtn) {
        var prevLabel = saveBtn.getAttribute("data-prev-label") || "Сохранить";
        saveBtn.disabled = false;
        if (okSave) {
          saveBtn.textContent = "Сохранено";
          setTimeout(function () {
            saveBtn.textContent = prevLabel;
          }, 1800);
        } else {
          saveBtn.textContent = "Ошибка";
          setTimeout(function () {
            saveBtn.textContent = prevLabel;
          }, 2200);
        }
      }
    }
    if (!form || !form.classList || !form.classList.contains("dream-sandbox-form")) return;
    var xhr = ev.detail && ev.detail.xhr;
    var ok = !!(xhr && xhr.status >= 200 && xhr.status < 300);
    finishSandboxState(form, ok, xhr);
  });

  document.body.addEventListener("htmx:responseError", function (ev) {
    var form = ev.detail && ev.detail.elt;
    var xhr = ev.detail && ev.detail.xhr;
    finishSandboxState(form, false, xhr);
  });

  document.body.addEventListener("htmx:sendError", function (ev) {
    var form = ev.detail && ev.detail.elt;
    if (form && form.classList && form.classList.contains("dream-sandbox-form")) {
      finishSandboxState(form, false, null);
    }
  });

  document.addEventListener(
    "submit",
    function (ev) {
      var form = ev.target;
      if (!form || form.id !== "stage1-test-form") return;
      var sub = ev.submitter;
      var phase = sub && sub.getAttribute ? sub.getAttribute("data-director-run-phase") : null;
      if (phase) {
        var ph = document.getElementById("stage1-phase");
        if (ph) ph.value = phase;
      }
    },
    true
  );

  document.addEventListener("click", function (ev) {
    var applyRefs = ev.target.closest("#stage1-apply-refs-bundle-btn");
    if (applyRefs) {
      ev.preventDefault();
      var pre = document.getElementById("stage1-references-bundle-pre");
      var ta = document.getElementById("stage1-references-plan-field");
      if (pre && ta) {
        ta.value = (pre.textContent || "").trim();
        try {
          ta.dispatchEvent(new Event("input", { bubbles: true }));
        } catch (e) {}
      }
      var phase = document.getElementById("stage1-phase");
      if (phase) phase.value = "keyframes";
      return;
    }
    var pullAsm = ev.target.closest("#assembler-pull-director-btn");
    if (pullAsm) {
      ev.preventDefault();
      pushDirectorOutputToAssembler(true);
      return;
    }
    var saveBtn = ev.target.closest("[data-save-scenarist-to-director]");
    if (saveBtn) {
      ev.preventDefault();
      saveCurrentStage0BToDirectorInput(true);
      return;
    }
    var btn = ev.target.closest("[data-clear-target]");
    if (!btn) return;
    var id = btn.getAttribute("data-clear-target");
    var node = id ? document.getElementById(id) : null;
    if (!node) return;
    node.innerHTML = '<p class="muted small">Тестовый вывод очищен. Запустите тест снова.</p>';
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

    // Dream Lite: провайдер часто отдаёт data:-URL; навигация target=_blank по гигантской строке даёт пустую вкладку.
    var dlA = ev.target.closest("a.dream-lite-frame-img-link, a.dream-lite-filmstrip-link");
    if (dlA) {
      var dlImg = dlA.querySelector("img");
      var src = dlImg && dlImg.src ? String(dlImg.src) : "";
      if (src.indexOf("data:") === 0) {
        ev.preventDefault();
        var w = window.open("about:blank", "_blank");
        if (!w) return;
        try {
          w.opener = null;
        } catch (e) {}
        var d = w.document;
        d.open();
        d.write(
          "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Просмотр кадра</title></head>" +
            "<body style=\"margin:0;background:#0f1419;text-align:center\">" +
            "<img alt=\"\" style=\"max-width:100%;height:auto;display:block;margin:0 auto\"/>" +
            "</body></html>"
        );
        d.close();
        var im = d.querySelector("img");
        if (im) im.src = src;
      }
    }
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

  function toolsFrameRootFromElt(elt) {
    if (!elt) return null;
    if (elt.id === "tools-frame-root") return elt;
    return elt.closest ? elt.closest("#tools-frame-root") : null;
  }

  function showToolsFrameLoadError(root, xhr) {
    if (!root) return;
    var status = xhr && typeof xhr.status === "number" ? xhr.status : 0;
    var rawBody = "";
    var detailStr = "";
    try {
      rawBody = xhr && xhr.responseText ? String(xhr.responseText) : "";
      if (rawBody.trim().indexOf("{") === 0) {
        var j = JSON.parse(rawBody);
        if (j.detail !== undefined) {
          detailStr = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        }
      }
    } catch (e) {}
    var body = detailStr || rawBody;

    var hint = "";
    if (status === 403) {
      hint =
        "Доступ к /dev разрешён только с loopback (127.0.0.1), localhost или частной сети. Если открываете приложение по публичному IP, используйте SSH port forward, например: ssh -L 8000:127.0.0.1:8000 user@host";
    } else if (status === 404) {
      if (detailStr === "Dev console disabled") {
        hint =
          "Консоль выключена в этом процессе: в окружении задайте DEV_DEBUG_UI=true (или DEBUG_CONSOLE=true) и полностью перезапустите uvicorn.";
      } else if (detailStr === "Not Found" || !detailStr) {
        hint =
          "Маршрут /dev не зарегистрирован: backend запущен без dev-роутера (часто DEV_DEBUG_UI=false в момент старта или переменная задана в системе и перекрывает .env). Нужен файл projects/content/.env с DEV_DEBUG_UI=true, рабочий каталог/запуск из корня этого проекта и перезапуск. Убедитесь, что в браузере открыт тот же хост:порт, куда смотрит uvicorn (не другой прокси/фронтенд).";
      } else {
        hint = "См. текст ответа ниже.";
      }
    } else if (status >= 500) {
      hint = "Ошибка сервера — смотрите логи uvicorn (сбор контекста Tools, Mongo, шаблон).";
    } else if (status === 0) {
      hint = "Сеть: сервер не отвечает, соединение сброшено или запрос заблокирован.";
    }
    root.innerHTML =
      '<div class="tools-frame-error box">' +
      "<p><strong>Не удалось загрузить Tools</strong> (HTTP " +
      status +
      ").</p>" +
      (hint ? '<p class="muted">' + escapeHtml(hint) + "</p>" : "") +
      (body
        ? '<pre class="mono muted tools-frame-error-detail">' + escapeHtml(body.slice(0, 1200)) + "</pre>"
        : "") +
      "</div>";
  }

  function onToolsFrameRequestFailed(ev) {
    var reqElt = ev.detail && ev.detail.elt;
    var xhr = ev.detail && ev.detail.xhr;
    var root = toolsFrameRootFromElt(reqElt);
    if (!root) return;
    showToolsFrameLoadError(root, xhr);
  }

  document.body.addEventListener("htmx:responseError", onToolsFrameRequestFailed);
  document.body.addEventListener("htmx:sendError", onToolsFrameRequestFailed);
  document.body.addEventListener("htmx:timeout", onToolsFrameRequestFailed);

  document.body.addEventListener("htmx:afterSwap", function (ev) {
    var d = ev.detail;
    var t = d && (d.target || d.elt);
    if (!t) return;
    onGlobalRefVisualSwapped(t);
    if (t.id === "gen-result") pushFromGenResult(t);
    if (t.id === "gen-result-qwen" || t.id === "openrouter-gen-result") {
      pushFromGenResult(t);
    }
    if (t.id === "message-rows") restoreMessageSelection();
    if (t.id === "tools-frame-root") initDevToolsTabs(t);
    if (
      t.id === "tools-frame-root" ||
      t.querySelector("#stage1-scenarist-json") ||
      t.id === "dream-stage1-prompt-lab" ||
      t.id === "dream-stage1-lab-mount" ||
      t.querySelector("#assembler-sandbox-form")
    ) {
      restoreStage0BDirectorState();
      restoreAssemblerWorkbench();
      initDirectorFocusAccordion(t);
      initDirectorPromptCards(t);
    }
    if (t.id === "panel-playground" || t.querySelector("[data-playground-accordion]")) {
      initPlaygroundAccordion(t);
    }
    if (t.id === "panel-playground" || t.querySelector("#form-video-job")) {
      initVideoJobPanel(t);
    }
    if (t.id === "dream-stage0a-test-result") {
      var json0a = t.querySelector("#stage0a-final-copy");
      var inp0b = document.getElementById("stage0b-beats-json");
      if (json0a && inp0b) {
        inp0b.value = (json0a.textContent || "").trim();
        renderStage0BBeatsPreview();
      }
      syncDreamTextFromBeatPlanner();
    }
    if (t.id === "dream-stage0b-test-result") {
      var json0b = t.querySelector("#stage0b-final-copy");
      var inp1 = document.getElementById("stage1-scenarist-json");
      var isLocked = isScenaristOutputLocked();
      if (json0b && inp1 && !isLocked) {
        inp1.value = json0b.textContent || "";
        try {
          localStorage.setItem(STAGE0B_SAVED_JSON_KEY, inp1.value || "");
        } catch (e) {}
        renderStage1ScenaristPreview();
      } else if (isLocked) {
        setStage0BHint("Зафиксировано: input Режиссёра не перезаписан", false);
      }
    }
    if (t.id === "dream-stage1-test-result") {
      hydrateGlobalRefImages(t);
      persistGlobalRefImagesFromContainer(t);
      initDirectorPreflight(t);
      pushDirectorOutputToAssembler(false);
      var wb = t.closest && t.closest(".director-workbench");
      if (wb) wb.setAttribute("data-focus", "output");
    }
    initDreamJsonHighlights(t);
    initAutosize(t);
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
      show(btn.getAttribute("data-tool-tab") || "tools");
    });
    show("tools");
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderHistory();
    restoreMessageSelection();
    initDevToolsTabs(document.getElementById("tools-frame-root"));
    initAutosize(document);
    initPlaygroundAccordion(document.getElementById("panel-playground"));
    initVideoJobPanel(document);
    restoreStage0BDirectorState();
    restoreAssemblerWorkbench();
    initDirectorFocusAccordion(document);
    initDirectorPromptCards(document);
    renderStage0BBeatsPreview();
    restoreStage1DreamText();
    renderStage1ScenaristPreview();
    initDirectorPreflight(document.getElementById("dream-stage1-test-result"));
    initDreamJsonHighlights(document);
  });
})();
