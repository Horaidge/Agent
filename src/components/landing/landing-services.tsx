import { SectionShell } from "@/components/ui/section-shell";

const blocks = [
  {
    title: "Smart Knowledge Base",
    text: "We structure corporate documents, product catalogs, policies, knowledge articles, presentations, and domain expertise into a unified knowledge layer that AI agents can reliably use.",
  },
  {
    title: "Knowledge Agents",
    text: "Specialized agents retrieve and reason over enterprise knowledge to provide accurate, contextual answers through voice, chat, or visual interfaces.",
  },
  {
    title: "Skill Agents",
    text: "Task-oriented agents execute business actions: generate reports, parse documents, update systems, route requests, collect data, and support operational workflows.",
  },
  {
    title: "Router Agent",
    text: "The orchestration layer that understands user intent, selects the right agent, controls the workflow, enforces policies, and returns one coherent answer to the user.",
  },
];

export function LandingServices() {
  return (
    <SectionShell
      id="what-we-build"
      title="What We Build"
      subtitle="Enterprise-grade AI systems"
    >
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        Enterprise-grade AI systems built around proprietary knowledge, specialized agents, and
        controlled orchestration.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {blocks.map((item) => (
          <article
            key={item.title}
            className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-5"
          >
            <h3 className="text-base font-medium text-[var(--color-polar-white)]">{item.title}</h3>
            <p className="mt-2 text-sm text-[var(--color-ash-gray)]">{item.text}</p>
          </article>
        ))}
      </div>
    </SectionShell>
  );
}
