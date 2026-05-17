import { VapiAgentWidget } from "@/components/agent/vapi-agent-widget";
import { SectionShell } from "@/components/ui/section-shell";

type LandingAgentZoneProps = {
  publicKey: string;
  assistantId: string;
};

export function LandingAgentZone({ publicKey, assistantId }: LandingAgentZoneProps) {
  return (
    <SectionShell
      id="agent-zone"
      title="Interactive Agent Interface"
      subtitle="AI-native interface layer"
      className="py-10 md:py-14"
      maxWidthClassName="max-w-[94rem]"
    >
      <p className="max-w-4xl text-base text-[var(--color-ash-gray)] md:text-lg">
        A cinematic interface for real-time voice and multimodal interaction with enterprise AI
        agents.
      </p>
      <p className="max-w-4xl text-sm text-[var(--color-ash-gray)] md:text-base">
        The sphere is not a chatbot window. It is an entry point into a live agentic experience -
        voice, chat, video demonstrations, and contextual guidance in one interface.
      </p>
      <VapiAgentWidget
        publicKey={publicKey}
        assistantId={assistantId}
        className="min-h-[56rem] md:min-h-[62rem]"
      />
      <div className="flex flex-wrap gap-2">
        {[
          "Ask to see Inspectra",
          "Show Anna multi-agent system",
          "Demonstrate Metallica digital twin",
          "Explain how Smart Knowledge Base works",
        ].map((hint) => (
          <span
            key={hint}
            className="mono rounded-full border border-[var(--color-border)] bg-[var(--color-deep-space)] px-3 py-1.5 text-xs text-[var(--color-ash-gray)]"
          >
            {hint}
          </span>
        ))}
      </div>
    </SectionShell>
  );
}
