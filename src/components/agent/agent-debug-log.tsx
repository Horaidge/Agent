"use client";

import { downloadDebugSessionSnapshot } from "@/shared/debug-session-storage";
import type { AgentChatMessage, AgentDebugEvent, AgentToolItem } from "@/components/agent/types";

type AgentDebugLogProps = {
  status: string;
  errorMessage?: string;
  messages: AgentChatMessage[];
  tools: AgentToolItem[];
  events: AgentDebugEvent[];
};

export function AgentDebugLog({ status, errorMessage, messages, tools, events }: AgentDebugLogProps) {
  const handleExport = () => {
    downloadDebugSessionSnapshot({
      updatedAt: new Date().toISOString(),
      status,
      errorMessage: errorMessage ?? null,
      transcriptMessages: messages,
      toolEvents: tools.map((item) => ({
        id: item.id,
        name: item.name,
        status: item.status,
        summary: item.summary,
        rawPayload: item.rawPayload,
        timestamp: new Date().toISOString(),
      })),
      debugEvents: events,
    });
  };

  const handleSendToServer = async () => {
    await fetch("/api/debug-ingest", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        createdAt: new Date().toISOString(),
        status,
        errorMessage: errorMessage ?? null,
        messages,
        tools,
        debugEvents: events,
      }),
    });
  };

  return (
    <details className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-black/20 p-3">
      <summary className="mono cursor-pointer text-[10px] uppercase tracking-[0.16em] text-[var(--color-ash-gray)]">
        WebRTC/VAPI debug log ({events.length})
      </summary>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleExport}
          className="mono rounded border border-[var(--color-border)] px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-[var(--color-polar-white)] hover:border-[var(--color-amber-glow)]"
        >
          Export JSON
        </button>
        <button
          type="button"
          onClick={handleSendToServer}
          className="mono rounded border border-[var(--color-border)] px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-[var(--color-polar-white)] hover:border-[var(--color-amber-glow)]"
        >
          Send to server
        </button>
      </div>
      <div className="mt-3 flex max-h-52 flex-col gap-2 overflow-auto">
        {events.length === 0 ? (
          <p className="text-sm text-[var(--color-ash-gray)]">События появятся после старта сессии.</p>
        ) : (
          events
            .slice()
            .reverse()
            .map((event) => (
              <div key={event.id} className="rounded border border-[var(--color-border)] p-2">
                <div className="mono mb-1 flex items-center justify-between text-[10px] uppercase tracking-[0.12em] text-[var(--color-ash-gray)]">
                  <span>{event.type}</span>
                  <span>{new Date(event.timestamp).toLocaleTimeString("ru-RU")}</span>
                </div>
                <pre className="overflow-auto text-xs leading-5 text-[var(--color-polar-white)]">
                  {event.payload}
                </pre>
              </div>
            ))
        )}
      </div>
    </details>
  );
}
