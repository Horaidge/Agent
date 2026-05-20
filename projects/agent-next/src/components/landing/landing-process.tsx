import { ScrollSectionStub } from "@/components/animations/scroll-section-stub";
import { SectionShell } from "@/components/ui/section-shell";

const processSteps = [
  {
    step: "1. User asks or speaks",
    text: "The interaction starts through voice, chat, avatar, kiosk, website, mobile app, or messenger.",
  },
  {
    step: "2. Router Agent understands the request",
    text: "The system identifies intent, context, required knowledge, and the right agent to handle the task.",
  },
  {
    step: "3. Knowledge Agents retrieve verified information",
    text: "The system searches structured proprietary knowledge instead of relying on generic model memory.",
  },
  {
    step: "4. Skill Agents execute actions",
    text: "When needed, agents trigger business workflows, prepare outputs, collect information, or update systems.",
  },
  {
    step: "5. User receives one clear answer",
    text: "The result is delivered as a natural conversation, supported by text, voice, visual content, or video.",
  },
];

export function LandingProcess() {
  return (
    <SectionShell id="system-flow" title="How the System Works" subtitle="Product logic">
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        Every DZEN.AI system is built around a controlled knowledge and agent architecture. The
        user interacts with one simple interface, while the system routes the request through the
        right knowledge, reasoning, and execution layers.
      </p>
      <div className="grid gap-4">
        {processSteps.map((item) => (
          <article
            key={item.step}
            className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4"
          >
            <p className="mono text-xs uppercase tracking-[0.1em] text-[var(--color-amber-glow)]">
              {item.step}
            </p>
            <p className="mt-2 text-sm text-[var(--color-ash-gray)]">{item.text}</p>
          </article>
        ))}
      </div>
      <ScrollSectionStub />
    </SectionShell>
  );
}
