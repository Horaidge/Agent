import { SectionShell } from "@/components/ui/section-shell";

const points = [
  "Enterprise-first architecture designed for controlled, domain-specific, auditable AI systems.",
  "Multi-agent expertise across knowledge agents, skill agents, router agents, and scenario orchestration.",
  "Voice and multimodal experience with real-time voice, chat, image understanding, and avatar-ready systems.",
  "Knowledge engineering focus: we build the knowledge layer that makes enterprise AI accurate and useful.",
  "Deployment flexibility across cloud, on-premise, web, mobile, kiosk, messenger, and avatar environments.",
];

export function LandingWhyDzen() {
  return (
    <SectionShell id="why-dzen" title="Why DZEN.AI" subtitle="Delivery credibility">
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        We combine conversational AI, knowledge engineering, multi-agent orchestration, voice
        technologies, computer vision, and enterprise deployment experience into one delivery team.
      </p>
      <ul className="grid gap-3">
        {points.map((point) => (
          <li
            key={point}
            className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4 text-sm text-[var(--color-ash-gray)]"
          >
            {point}
          </li>
        ))}
      </ul>
    </SectionShell>
  );
}
