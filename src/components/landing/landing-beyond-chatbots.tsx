import { SectionShell } from "@/components/ui/section-shell";

const compareRows = [
  {
    chatbots: "answers questions.",
    dzen: "understands intent and routes the task.",
  },
  {
    chatbots: "depends on scripted flows.",
    dzen: "uses structured knowledge and reasoning.",
  },
  {
    chatbots: "stops at conversation.",
    dzen: "can support real business execution.",
  },
];

export function LandingBeyondChatbots() {
  return (
    <SectionShell id="beyond-chatbots" title="Beyond Chatbots" subtitle="Positioning">
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        Traditional chatbots answer isolated questions. Multi-agent systems solve operational
        tasks.
      </p>
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        Our agents do not simply generate text. They retrieve verified knowledge, understand
        context, collaborate with other agents, trigger tools, support voice and visual
        interaction, and operate within enterprise rules.
      </p>
      <div className="grid gap-3">
        {compareRows.map((row, index) => (
          <div
            key={`${row.chatbots}-${index}`}
            className="grid gap-2 rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4 md:grid-cols-2"
          >
            <p className="text-sm text-[var(--color-ash-gray)]">
              <span className="mono mr-2 text-xs uppercase tracking-[0.08em] text-[var(--color-ash-gray)]">
                Chatbot:
              </span>
              {row.chatbots}
            </p>
            <p className="text-sm text-[var(--color-polar-white)]">
              <span className="mono mr-2 text-xs uppercase tracking-[0.08em] text-[var(--color-amber-glow)]">
                DZEN.AI agent:
              </span>
              {row.dzen}
            </p>
          </div>
        ))}
      </div>
    </SectionShell>
  );
}
