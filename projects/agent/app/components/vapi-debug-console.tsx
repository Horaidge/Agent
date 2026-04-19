"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { TranscriptProbe } from "@/hooks/use-vapi-call";
import { normalizeIncomingToolCall } from "@/lib/vapi-tool-calls";

type Tab = "timeline" | "tools" | "speech" | "raw";
type Filter = "All" | "Messages" | "Tools" | "Speech" | "Errors";

type TimelineEntry = {
  id: string;
  ts: string;
  category: Filter;
  label: string;
  details?: string;
};

type ToolRow = {
  id: string;
  ts: string;
  name: string;
  arguments: string;
  status: "requested" | "result" | "failed";
  duration: string;
};

function fmtTs(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("ru-RU");
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function extractConversationMessages(raw: unknown): Array<{ role: "user" | "assistant"; text: string }> {
  if (!raw || typeof raw !== "object") return [];
  const root = raw as Record<string, unknown>;
  const source =
    (Array.isArray(root.messages) && root.messages) ||
    (Array.isArray(root.conversation) && root.conversation) ||
    ((root.conversation && typeof root.conversation === "object" && Array.isArray((root.conversation as Record<string, unknown>).messages))
      ? ((root.conversation as Record<string, unknown>).messages as unknown[])
      : null);
  if (!source) return [];

  const out: Array<{ role: "user" | "assistant"; text: string }> = [];
  for (const item of source) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const role = row.role === "assistant" ? "assistant" : row.role === "user" ? "user" : null;
    if (!role) continue;
    const text = typeof row.text === "string"
      ? row.text
      : typeof row.content === "string"
        ? row.content
        : typeof row.message === "string"
          ? row.message
          : "";
    const normalized = text.trim();
    if (!normalized) continue;
    out.push({ role, text: normalized });
  }
  return out;
}

function extractToolCalls(raw: unknown): Array<{ name: string; args: unknown }> {
  if (!raw || typeof raw !== "object") return [];
  const obj = raw as Record<string, unknown>;

  if (Array.isArray(obj.toolCalls)) {
    return (obj.toolCalls as unknown[]).map((c) => {
      const n = normalizeIncomingToolCall(c);
      return { name: n.rawName ?? "unknown", args: n.rawArgs };
    });
  }
  if (obj.type === "tool-call" && obj.toolCall && typeof obj.toolCall === "object") {
    const n = normalizeIncomingToolCall(obj.toolCall);
    return [{ name: n.rawName ?? "unknown", args: n.rawArgs }];
  }
  return [];
}

export function VapiDebugConsole({ logs, onClear }: { logs: TranscriptProbe[]; onClear: () => void }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("timeline");
  const [filter, setFilter] = useState<Filter>("All");
  const [showRaw, setShowRaw] = useState(false);
  const [showPartials, setShowPartials] = useState(false);
  const [showModelTokens, setShowModelTokens] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const { timeline, tools, speech, rawLogs } = useMemo(() => {
    const t: TimelineEntry[] = [];
    const toolRows: ToolRow[] = [];
    const speechRows: TimelineEntry[] = [];
    let lastUser = "";
    let lastAssistant = "";

    for (const log of logs) {
      const ts = fmtTs(log.ts);
      const id = `${log.seq}`;

      if (log.eventType === "conversation-update") {
        const msgs = extractConversationMessages(log.raw);
        const latestUser = [...msgs].reverse().find((m) => m.role === "user")?.text ?? "";
        const latestAssistant = [...msgs].reverse().find((m) => m.role === "assistant")?.text ?? "";
        if (latestUser && latestUser !== lastUser) {
          t.push({ id: `${id}-u`, ts, category: "Messages", label: "user message committed", details: latestUser });
          lastUser = latestUser;
        }
        if (latestAssistant && latestAssistant !== lastAssistant) {
          t.push({ id: `${id}-a`, ts, category: "Messages", label: "assistant message committed", details: latestAssistant });
          lastAssistant = latestAssistant;
        }
        continue;
      }

      if (log.eventType === "transcript") {
        if (log.transcriptType === "partial" && !showPartials) continue;
        if (showModelTokens && log.role === "assistant") {
          t.push({
            id: `${id}-token`,
            ts,
            category: "Messages",
            label: `${log.role} ${log.transcriptType ?? ""}`,
            details: log.transcript ?? "",
          });
        }
        continue;
      }

      if (log.source === "speech-update") {
        const speaking = log.status === "started";
        const label =
          log.role === "assistant"
            ? speaking
              ? "assistant started"
              : "assistant stopped"
            : speaking
              ? "user started"
              : "user stopped";
        const entry = { id: `${id}-s`, ts, category: "Speech" as Filter, label };
        t.push(entry);
        speechRows.push(entry);
        continue;
      }

      const calls = extractToolCalls(log.raw);
      if (calls.length > 0) {
        for (const c of calls) {
          t.push({
            id: `${id}-tool-${c.name}`,
            ts,
            category: "Tools",
            label: `tool requested: ${c.name}`,
            details: safeStringify(c.args),
          });
          toolRows.push({
            id: `${id}-${c.name}`,
            ts,
            name: c.name,
            arguments: safeStringify(c.args),
            status: "requested",
            duration: "—",
          });
        }
        continue;
      }

      if (log.eventType === "video-shown") {
        const details = safeStringify(log.raw);
        t.push({ id: `${id}-video-show`, ts, category: "Tools", label: "UI: video inserted into chat", details });
        toolRows.push({
          id: `${id}-show-result`,
          ts,
          name: "show_video",
          arguments: details,
          status: "result",
          duration: "instant",
        });
        continue;
      }

      if (log.eventType === "video-hidden") {
        t.push({ id: `${id}-video-hide`, ts, category: "Tools", label: "UI: video hidden" });
        toolRows.push({
          id: `${id}-hide-result`,
          ts,
          name: "hide_video",
          arguments: "{}",
          status: "result",
          duration: "instant",
        });
        continue;
      }

      if (log.source === "error" || /fail|invalid|missing|unsupported|error/i.test(log.eventType)) {
        const details = safeStringify(log.raw);
        t.push({ id: `${id}-err`, ts, category: "Errors", label: log.eventType, details });
        toolRows.push({
          id: `${id}-tool-err`,
          ts,
          name: "tool",
          arguments: details,
          status: "failed",
          duration: "—",
        });
      }
    }

    return { timeline: t, tools: toolRows, speech: speechRows, rawLogs: logs };
  }, [logs, showModelTokens, showPartials]);

  const filteredTimeline = useMemo(
    () => (filter === "All" ? timeline : timeline.filter((e) => e.category === filter)),
    [filter, timeline]
  );

  useEffect(() => {
    if (!autoScroll) return;
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
  }, [autoScroll, tab, filteredTimeline, tools, speech, rawLogs]);

  return (
    <section
      className="w-full rounded-2xl border"
      style={{ background: "rgba(8,9,12,0.7)", borderColor: "rgba(255,255,255,0.08)" }}
    >
      <div className="flex flex-wrap items-center gap-2 border-b p-2" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="rounded-full px-2.5 py-1 text-[11px]"
          style={{ border: "1px solid rgba(255,255,255,0.12)" }}
        >
          {open ? "Hide Debug Console" : "Show Debug Console"}
        </button>
        <span className="text-[11px] text-[rgba(170,178,198,0.7)]">{logs.length} events</span>
        <button type="button" onClick={onClear} className="rounded-full px-2.5 py-1 text-[11px]" style={{ border: "1px solid rgba(255,255,255,0.12)" }}>
          Clear
        </button>
      </div>

      {open && (
        <div className="p-2">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            {(["timeline", "tools", "speech", "raw"] as Tab[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setTab(k)}
                className="rounded-full px-2.5 py-1 text-[11px] capitalize"
                style={{
                  border: "1px solid rgba(255,255,255,0.12)",
                  background: tab === k ? "rgba(124, 58, 237, 0.18)" : "transparent",
                }}
              >
                {k}
              </button>
            ))}

            <div className="ml-auto flex flex-wrap gap-1.5">
              {(["All", "Messages", "Tools", "Speech", "Errors"] as Filter[]).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFilter(f)}
                  className="rounded-full px-2 py-0.5 text-[10px]"
                  style={{
                    border: "1px solid rgba(255,255,255,0.1)",
                    background: filter === f ? "rgba(34, 211, 238, 0.15)" : "transparent",
                  }}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-2 flex flex-wrap gap-2 text-[10px] text-[rgba(170,178,198,0.85)]">
            <Toggle label="Show raw" checked={showRaw} onChange={setShowRaw} />
            <Toggle label="Show partials" checked={showPartials} onChange={setShowPartials} />
            <Toggle label="Show model tokens" checked={showModelTokens} onChange={setShowModelTokens} />
            <Toggle label="Auto-scroll" checked={autoScroll} onChange={setAutoScroll} />
          </div>

          <div
            ref={scrollerRef}
            className="chat-scroll-area overflow-auto rounded-xl border p-2"
            style={{ maxHeight: 280, borderColor: "rgba(255,255,255,0.08)", background: "rgba(5,6,8,0.45)" }}
          >
            {tab === "timeline" && (
              <div className="space-y-1.5 text-[11px]">
                {filteredTimeline.map((e) => (
                  <div key={e.id} className="rounded-lg border p-1.5" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
                    <div className="text-[10px] text-[rgba(140,150,180,0.7)]">{e.ts}</div>
                    <div>{e.label}</div>
                    {e.details && <div className="mt-0.5 text-[rgba(170,178,198,0.7)]">{e.details}</div>}
                  </div>
                ))}
              </div>
            )}

            {tab === "tools" && (
              <table className="w-full text-left text-[11px]">
                <thead className="text-[10px] text-[rgba(140,150,180,0.75)]">
                  <tr>
                    <th className="py-1">time</th>
                    <th className="py-1">tool name</th>
                    <th className="py-1">arguments</th>
                    <th className="py-1">status</th>
                    <th className="py-1">duration</th>
                  </tr>
                </thead>
                <tbody>
                  {tools.map((r) => (
                    <tr key={r.id} className="border-t" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
                      <td className="py-1 align-top">{r.ts}</td>
                      <td className="py-1 align-top">{r.name}</td>
                      <td className="py-1 align-top break-all text-[rgba(170,178,198,0.8)]">{r.arguments}</td>
                      <td className="py-1 align-top">{r.status}</td>
                      <td className="py-1 align-top">{r.duration}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {tab === "speech" && (
              <div className="space-y-1.5 text-[11px]">
                {speech.map((e) => (
                  <div key={e.id} className="rounded-lg border p-1.5" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
                    <div className="text-[10px] text-[rgba(140,150,180,0.7)]">{e.ts}</div>
                    <div>{e.label}</div>
                  </div>
                ))}
              </div>
            )}

            {tab === "raw" && showRaw && (
              <pre className="whitespace-pre-wrap break-words text-[10px] leading-relaxed text-[rgba(200,206,220,0.8)]">
                {JSON.stringify(rawLogs, null, 2)}
              </pre>
            )}
            {tab === "raw" && !showRaw && (
              <div className="text-[11px] text-[rgba(170,178,198,0.7)]">
                Raw скрыт. Включите тумблер <b>Show raw</b>.
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="rounded-full px-2 py-0.5"
      style={{
        border: "1px solid rgba(255,255,255,0.1)",
        background: checked ? "rgba(124, 58, 237, 0.18)" : "transparent",
      }}
    >
      {label}: {checked ? "on" : "off"}
    </button>
  );
}
