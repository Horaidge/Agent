import { SectionShell } from "@/components/ui/section-shell";

const capabilities = [
  {
    title: "Talk",
    text: "Voice AI agents for inbound and outbound calls, customer service, internal support, consultations, and guided scenarios.",
  },
  {
    title: "See",
    text: "Computer vision for image recognition, diagnostics, document understanding, visual inspection, and multimodal analysis.",
  },
  {
    title: "Reason",
    text: "LLM-powered reasoning over proprietary knowledge, business rules, documents, policies, and contextual data.",
  },
  {
    title: "Execute",
    text: "Skill agents that can trigger workflows, prepare reports, collect information, update records, and support transactions.",
  },
  {
    title: "Scale",
    text: "Omnichannel deployment across website, mobile app, Telegram, WhatsApp, call center, kiosk, and 3D avatar environments.",
  },
];

export function LandingCoreCapabilities() {
  return (
    <SectionShell id="capabilities" title="Core Capabilities" subtitle="System scope">
      <div className="grid gap-3 md:grid-cols-2">
        {capabilities.map((item) => (
          <article
            key={item.title}
            className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-5"
          >
            <h3 className="text-base text-[var(--color-polar-white)]">{item.title}</h3>
            <p className="mt-2 text-sm text-[var(--color-ash-gray)]">{item.text}</p>
          </article>
        ))}
      </div>
    </SectionShell>
  );
}
