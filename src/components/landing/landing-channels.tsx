import { SectionShell } from "@/components/ui/section-shell";

const channels = [
  {
    title: "Website Widget",
    text: "Embedded AI interface for product guidance, support, and consultations.",
  },
  {
    title: "Voice Agent",
    text: "Real-time AI agent for inbound and outbound calls.",
  },
  {
    title: "Mobile App",
    text: "AI assistance inside enterprise or customer-facing mobile products.",
  },
  {
    title: "Messengers",
    text: "Telegram, WhatsApp, and other text-based channels.",
  },
  {
    title: "Interactive Kiosks",
    text: "Voice and avatar-based interaction in public service centers, offices, exhibitions, and retail locations.",
  },
  {
    title: "3D Avatar / Unreal Engine",
    text: "Human-like visual interface for premium, public-facing, or event-based experiences.",
  },
];

export function LandingChannels() {
  return (
    <SectionShell id="channels" title="One Intelligence Layer. Any Interface." subtitle="Deployment channels">
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        DZEN.AI systems can be deployed wherever users need access to knowledge, guidance, or
        action - from websites and mobile apps to call centers, messengers, kiosks, and 3D
        avatars.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {channels.map((item) => (
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
