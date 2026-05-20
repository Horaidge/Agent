import { SectionShell } from "@/components/ui/section-shell";

const knowledgeBlocks = [
  {
    title: "Documents",
    text: "Policies, manuals, presentations, reports, FAQs, contracts, product descriptions, and internal knowledge articles.",
  },
  {
    title: "Structure",
    text: "Semantic tagging, topic segmentation, metadata, access boundaries, and version control.",
  },
  {
    title: "Retrieval",
    text: "Agents search by meaning, context, topic, and user intent - not only by keywords.",
  },
  {
    title: "Governance",
    text: "The system can respect roles, permissions, approved sources, and enterprise rules.",
  },
  {
    title: "Continuous Improvement",
    text: "Real user interactions can be reviewed, analyzed, and used to improve the knowledge base over time.",
  },
];

export function LandingKnowledgeBase() {
  return (
    <SectionShell id="knowledge-base" title="Smart Knowledge Base" subtitle="Core platform layer">
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        The proprietary knowledge layer behind every enterprise AI agent.
      </p>
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        A Smart Knowledge Base transforms fragmented corporate information into a structured,
        searchable, and governed knowledge system. It allows AI agents to provide accurate,
        contextual, and domain-specific answers instead of generic responses.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {knowledgeBlocks.map((item) => (
          <article
            key={item.title}
            className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4"
          >
            <h3 className="text-sm font-medium text-[var(--color-polar-white)]">{item.title}</h3>
            <p className="mt-2 text-sm text-[var(--color-ash-gray)]">{item.text}</p>
          </article>
        ))}
      </div>
    </SectionShell>
  );
}
