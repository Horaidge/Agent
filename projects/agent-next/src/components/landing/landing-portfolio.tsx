import { SectionShell } from "@/components/ui/section-shell";

const systemsWithVideo = [
  {
    name: "Inspectra",
    subtitle: "AI agent for regulatory, compliance, and control workflows.",
    text: "Inspectra provides consultation and decision support for citizens, businesses, and government teams through real-time voice and chat interaction.",
    videoKey: "agent_1",
    cta: "Watch Inspectra Demo",
  },
  {
    name: "Anna",
    subtitle: "Multi-agent assistant for a major European capital city IT department.",
    text: "Anna supports citizens and internal teams with a Smart Knowledge Base and specialized agents for retrieval, dialogue understanding, analytics, and task support.",
    videoKey: "agent_2",
    cta: "Watch Anna Demo",
  },
  {
    name: "Ivan Polevoy",
    subtitle: "AI expert interface for domain-specific consultation and guided interaction.",
    text: "Demonstrates how an AI agent can act as a recognizable expert interface with natural conversation and structured answers.",
    videoKey: "agent_3",
    cta: "Watch Ivan Polevoy Demo",
  },
  {
    name: "Metallica",
    subtitle: "Digital twin for a large industrial corporation.",
    text: "Metallica unifies fragmented corporate data into a Smart Knowledge Base and provides 24/7 decision support for employees.",
    videoKey: "agent_4",
    cta: "Watch Metallica Demo",
  },
];

const extraSystems = [
  {
    name: "Digital Twin of Agronomist",
    subtitle: "AI assistant for agricultural decision support.",
    text: "Supports agronomists and farmers with fertilizer logic, crop recommendations, visual diagnostics, and real-time guidance.",
  },
  {
    name: "Idram Multi-Agent System",
    subtitle: "Conversational AI for fintech service continuity.",
    text: "Supports customer communication during service outages, logs interactions, and drives outbound notifications on service recovery.",
  },
];

export function LandingPortfolio() {
  return (
    <SectionShell
      id="portfolio"
      title="Selected Multi-Agent Systems"
      subtitle="Enterprise portfolio"
    >
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        Examples of enterprise AI systems developed for public sector, fintech, industrial, and
        agricultural use cases.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {systemsWithVideo.map((item) => (
          <article
            key={item.name}
            className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-5"
          >
            <h3 className="text-lg text-[var(--color-polar-white)]">{item.name}</h3>
            <p className="mt-1 text-sm font-medium text-[var(--color-polar-white)]">{item.subtitle}</p>
            <p className="mt-3 text-sm text-[var(--color-ash-gray)]">{item.text}</p>
            <div className="mt-4 flex items-center justify-between">
              <a href="#agent-zone" className="text-sm text-[var(--color-amber-glow)] hover:underline">
                {item.cta}
              </a>
              <span className="mono rounded-full border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-ash-gray)]">
                {item.videoKey}
              </span>
            </div>
          </article>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {extraSystems.map((item) => (
          <article
            key={item.name}
            className="rounded-[var(--radius-default)] border border-[var(--color-border)] p-5"
          >
            <h3 className="text-base text-[var(--color-polar-white)]">{item.name}</h3>
            <p className="mt-1 text-sm text-[var(--color-polar-white)]">{item.subtitle}</p>
            <p className="mt-2 text-sm text-[var(--color-ash-gray)]">{item.text}</p>
          </article>
        ))}
      </div>
    </SectionShell>
  );
}
