import { MotionFade } from "@/components/animations/motion-fade";
import { UIButton } from "@/components/ui/button";

export function LandingHero() {
  return (
    <section className="border-b border-[var(--color-border)] px-6 py-20 md:py-24">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <MotionFade>
          <p className="mono text-xs uppercase tracking-[0.18em] text-[var(--color-amber-glow)]">
            DZEN.AI
          </p>
        </MotionFade>
        <MotionFade delay={0.07}>
          <h1 className="max-w-5xl text-[var(--text-display)] leading-[1.02]">
            Multi-Agent AI Systems for Enterprise Operations
          </h1>
        </MotionFade>
        <MotionFade delay={0.12}>
          <p className="max-w-4xl text-[var(--text-subheading)] text-[var(--color-polar-white)]">
            We build controlled AI agent ecosystems that talk, see, reason, retrieve proprietary
            knowledge, and execute business workflows across any channel.
          </p>
        </MotionFade>
        <MotionFade delay={0.16}>
          <p className="max-w-4xl text-base text-[var(--color-ash-gray)] md:text-lg">
            From smart knowledge bases and RAG architectures to voice agents, avatars, computer
            vision, and workflow automation - DZEN.AI turns fragmented enterprise knowledge into
            operational intelligence.
          </p>
        </MotionFade>
        <MotionFade delay={0.2}>
          <div className="grid gap-3 md:grid-cols-3">
            <article className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4">
              <h3 className="text-sm font-medium text-[var(--color-polar-white)]">Voice & Chat AI Agents</h3>
              <p className="mt-2 text-sm text-[var(--color-ash-gray)]">
                Real-time human-like interaction across web, mobile, messengers, kiosks, and call
                centers.
              </p>
            </article>
            <article className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4">
              <h3 className="text-sm font-medium text-[var(--color-polar-white)]">Smart Knowledge Base</h3>
              <p className="mt-2 text-sm text-[var(--color-ash-gray)]">
                Structured proprietary knowledge layer for accurate, governed, domain-specific
                answers.
              </p>
            </article>
            <article className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4">
              <h3 className="text-sm font-medium text-[var(--color-polar-white)]">
                Multi-Agent Orchestration
              </h3>
              <p className="mt-2 text-sm text-[var(--color-ash-gray)]">
                Router, knowledge, and skill agents working together to solve complex enterprise
                tasks.
              </p>
            </article>
          </div>
        </MotionFade>
        <MotionFade delay={0.24}>
          <div className="flex flex-wrap items-center gap-3">
            <a href="#what-we-build">
              <UIButton className="border border-[var(--color-border)] bg-[var(--color-amber-glow)]/10">
                Explore Systems
              </UIButton>
            </a>
            <a href="#agent-zone">
              <UIButton variant="secondaryGhost" className="border border-[var(--color-border)]">
                Watch Agent Demo
              </UIButton>
            </a>
          </div>
        </MotionFade>
      </div>
    </section>
  );
}
