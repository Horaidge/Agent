import { AgentInput } from "@/components/agent/agent-input";
import { AgentMessageList } from "@/components/agent/agent-message-list";
import type { AgentChatMessage } from "@/components/agent/types";

type AgentChatPanelProps = {
  messages: AgentChatMessage[];
  onSendMessage: (message: string) => void;
  modeLabel?: string;
  errorMessage?: string;
};

export function AgentChatPanel({
  messages,
  onSendMessage,
  modeLabel = "dialog",
  errorMessage,
}: AgentChatPanelProps) {
  return (
    <section className="flex h-[34rem] min-w-0 w-full max-w-none flex-col overflow-hidden rounded-2xl border border-white/12 bg-[linear-gradient(165deg,rgba(255,255,255,0.06),rgba(8,8,10,0.86)_34%,rgba(8,8,10,0.9))] shadow-[0_20px_80px_rgba(0,0,0,0.4)] backdrop-blur-xl md:h-[38rem]">
      <header className="flex min-w-0 flex-wrap items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
        <p className="text-base">Agent session</p>
        <p className="mono truncate text-[10px] uppercase tracking-[0.14em] text-[var(--color-ash-gray)] opacity-80">
          {modeLabel}
        </p>
      </header>

      {errorMessage ? (
        <div className="border-b border-[var(--color-border)] px-4 py-3">
          <p className="rounded border border-red-500/35 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {errorMessage}
          </p>
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-3 pb-3 pt-2 md:px-4 md:pb-4">
          <div className="mb-2 flex min-w-0 flex-wrap items-center justify-between gap-2">
            <p className="mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-amber-glow)]">
              Conversation
            </p>
            <p className="mono text-[10px] uppercase tracking-[0.12em] text-[var(--color-ash-gray)] opacity-75">
              {messages.length} messages
            </p>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto rounded-[var(--radius-default)] border border-white/10 bg-[linear-gradient(180deg,rgba(11,12,16,0.88),rgba(9,9,13,0.72))] p-3 md:p-4">
            <AgentMessageList messages={messages} />
          </div>
        </div>

        <div className="border-t border-white/10 px-3 py-3 md:px-4 md:py-4">
          <AgentInput onSend={onSendMessage} />
        </div>
      </div>
    </section>
  );
}
