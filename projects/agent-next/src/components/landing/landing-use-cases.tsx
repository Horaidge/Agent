import { SectionShell } from "@/components/ui/section-shell";

const useCases = [
  {
    title: "Customer Service",
    text: "AI agents for inbound support, FAQ automation, service updates, complaint handling, call routing, and operator fallback.",
  },
  {
    title: "Sales & Marketing",
    text: "Lead qualification, product consultation, upsell and cross-sell scenarios, personalized offers, campaign support, and customer reactivation.",
  },
  {
    title: "Internal Knowledge Access",
    text: "Instant access to policies, documents, presentations, product materials, market research, and internal procedures.",
  },
  {
    title: "Compliance & Control",
    text: "Guidance on regulations, inspection processes, incident updates, audit support, and controlled access to sensitive knowledge.",
  },
  {
    title: "Industrial Decision Support",
    text: "Product catalog navigation, expert recommendations, training support, technical validation, and internal knowledge preservation.",
  },
  {
    title: "Agriculture & Field Expertise",
    text: "Crop recommendations, fertilizer logic, visual diagnostics, expert guidance, and region-specific decision support.",
  },
  {
    title: "Banking & Fintech",
    text: "Card and policy status updates, financial product consultation, debt reminders, user verification, service notifications, and contact center automation.",
  },
];

export function LandingUseCases() {
  return (
    <SectionShell id="use-cases" title="Enterprise Use Cases" subtitle="Adaptable architecture">
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        The same architecture can be adapted to customer service, internal operations, sales,
        training, compliance, and decision support.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {useCases.map((item) => (
          <article
            key={item.title}
            className="rounded-[var(--radius-default)] border border-[var(--color-border)] p-4"
          >
            <h3 className="text-sm font-medium text-[var(--color-polar-white)]">{item.title}</h3>
            <p className="mt-2 text-sm text-[var(--color-ash-gray)]">{item.text}</p>
          </article>
        ))}
      </div>
    </SectionShell>
  );
}
