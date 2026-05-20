import Link from "next/link";
import { SectionShell } from "@/components/ui/section-shell";
import { UIButton } from "@/components/ui/button";

export function LandingContact() {
  return (
    <SectionShell id="contact" title="Build Your Enterprise AI Agent Ecosystem" subtitle="Final CTA">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-6">
        <p className="max-w-3xl text-[var(--color-ash-gray)]">
          If your organization relies on fragmented knowledge, repetitive service operations,
          complex documentation, or expert-heavy workflows, DZEN.AI can turn this into a
          controlled multi-agent system.
        </p>
        <div className="flex items-center gap-3">
          <a href="#agent-zone">
            <UIButton className="border border-[var(--color-border)] bg-[var(--color-amber-glow)]/10">
              Request a Demo
            </UIButton>
          </a>
          <Link href="/login">
            <UIButton variant="secondaryGhost" className="border border-[var(--color-border)]">
              Discuss Your Use Case
            </UIButton>
          </Link>
        </div>
      </div>
      <p className="mono text-xs text-[var(--color-ash-gray)]">
        DZEN.AI - Multi-Agent Systems for enterprise knowledge, service, and operational
        intelligence.
      </p>
    </SectionShell>
  );
}
