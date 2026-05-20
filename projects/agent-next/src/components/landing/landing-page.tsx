"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import { VapiAgentWidget } from "@/components/agent/vapi-agent-widget";
import { CasesShowcase } from "@/components/cases/cases-showcase";

type LandingPageProps = {
  publicKey: string;
  assistantId: string;
};

export function LandingPage({ publicKey, assistantId }: LandingPageProps) {
  const [activeTab, setActiveTab] = useState<"agent" | "cases">("agent");

  return (
    <main className="relative min-h-[205dvh] overflow-hidden bg-[var(--color-midnight-void)] px-3 pb-16 pt-3 text-[var(--color-polar-white)] md:px-5 md:pb-24 md:pt-5">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(140%_95%_at_22%_-15%,rgba(255,255,255,0.08),rgba(16,17,22,0.92)_44%,rgba(8,9,12,1)_100%)]" />
      <div className="pointer-events-none absolute inset-x-[-16%] -bottom-[16%] h-[76%] bg-[radial-gradient(84%_74%_at_50%_100%,rgba(231,197,154,0.18),rgba(12,13,18,0.84)_46%,rgba(8,9,12,0)_100%)] blur-3xl" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(8,9,12,0.18),rgba(8,9,12,0.46)_36%,rgba(8,9,12,0.72)_100%)]" />

      <section className="relative z-10 mx-auto flex w-full max-w-[132rem] flex-col overflow-hidden rounded-[2.1rem] bg-[linear-gradient(180deg,rgba(18,19,24,0.82),rgba(11,12,16,0.7))]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_18%,rgba(231,197,154,0.12),rgba(8,8,10,0)_38%)]" />
        <header className="relative z-10 flex items-center justify-between border-b border-white/10 px-6 py-4">
          <div className="mono text-sm uppercase tracking-[0.35em] text-[var(--color-polar-white)]">
            DAVID <span className="text-[var(--color-amber-glow)]">•</span>
          </div>
          <nav className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("agent")}
              className={`relative rounded-full px-5 py-2 text-sm transition-colors ${
                activeTab === "agent"
                  ? "text-[var(--color-polar-white)]"
                  : "text-[var(--color-ash-gray)] hover:text-[var(--color-polar-white)]"
              }`}
            >
              Agent
              {activeTab === "agent" ? (
                <span className="absolute inset-x-4 -bottom-2 h-px bg-[var(--color-amber-glow)] shadow-[0_0_12px_rgba(231,197,154,0.45)]" />
              ) : null}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("cases")}
              className={`relative rounded-full px-5 py-2 text-sm transition-colors ${
                activeTab === "cases"
                  ? "text-[var(--color-polar-white)]"
                  : "text-[var(--color-ash-gray)] hover:text-[var(--color-polar-white)]"
              }`}
            >
              Cases
              {activeTab === "cases" ? (
                <span className="absolute inset-x-4 -bottom-2 h-px bg-[var(--color-amber-glow)] shadow-[0_0_12px_rgba(231,197,154,0.45)]" />
              ) : null}
            </button>
          </nav>
          <div className="h-8 w-8 rounded-full border border-white/15 bg-black/25" />
        </header>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.1, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="relative z-10 px-4 py-4 md:px-6 md:py-5"
        >
          {activeTab === "agent" ? (
            <VapiAgentWidget
              publicKey={publicKey}
              assistantId={assistantId}
              className="min-h-[74rem] md:min-h-[88rem]"
            />
          ) : (
            <CasesShowcase />
          )}
        </motion.div>
      </section>
    </main>
  );
}
