import { AgentDebugLog } from "@/components/agent/agent-debug-log";
import { AgentToolRenderer } from "@/components/agent/agent-tool-renderer";
import type { AgentChatMessage, AgentDebugEvent, AgentToolItem } from "@/components/agent/types";

type AgentObservabilityPanelProps = {
  status: string;
  errorMessage?: string;
  messages: AgentChatMessage[];
  tools: AgentToolItem[];
  debugEvents: AgentDebugEvent[];
};

export function AgentObservabilityPanel({
  status,
  errorMessage,
  messages,
  tools,
  debugEvents,
}: AgentObservabilityPanelProps) {
  return (
    <section className="relative z-10 mt-4 rounded-xl border border-[var(--color-border)] bg-[rgba(8,8,8,0.75)] p-4 backdrop-blur">
      <header className="mb-3 flex items-center justify-between">
        <p className="mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-ash-gray)]">
          Runtime Observability
        </p>
        <p className="mono text-[10px] uppercase tracking-[0.12em] text-[var(--color-ash-gray)]">
          tools: {tools.length} | events: {debugEvents.length}
        </p>
      </header>

      <div className="flex flex-col gap-3">
        <AgentToolRenderer items={tools} />
        <AgentDebugLog
          status={status}
          errorMessage={errorMessage}
          messages={messages}
          tools={tools}
          events={debugEvents}
        />
      </div>
    </section>
  );
}
