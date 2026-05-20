"use client";

import { motion } from "framer-motion";

interface InfoPanelProps {
  section: string | null;
  onClose: () => void;
}

const sections: Record<
  string,
  { title: string; subtitle: string; items: string[] }
> = {
  Platform: {
    title: "Platform",
    subtitle: "Multi-agent control plane",
    items: [
      "Smart knowledge base with contextual retrieval",
      "Agents that act — tools, workflows, systems",
      "Voice, text, and multimodal surfaces",
      "Observable runs and guardrails",
    ],
  },
  "Use Cases": {
    title: "Use Cases",
    subtitle: "Where teams ship Dzen.AI first",
    items: [
      "Customer support and triage",
      "Internal ops and knowledge copilots",
      "Documents, policies, and compliance Q&A",
      "Omnichannel handoff to humans when needed",
    ],
  },
  "How It Works": {
    title: "How It Works",
    subtitle: "Architecture you can reason about",
    items: [
      "Router layer — intent and policy",
      "Knowledge layer — RAG and memory",
      "Skills layer — APIs, tools, transactions",
      "Orchestration — state, retries, audit",
    ],
  },
  Integrations: {
    title: "Integrations",
    subtitle: "Connect to the systems you already use",
    items: [
      "REST and webhooks for custom backends",
      "CRM, ticketing, and data warehouses",
      "SSO and enterprise identity patterns",
      "Sandbox keys and staged rollouts",
    ],
  },
  Architecture: {
    title: "Architecture",
    subtitle: "Built for reliability at the edge",
    items: [
      "Composable agents and skills",
      "Vector stores and hybrid retrieval",
      "Latency-aware voice and text paths",
      "Logging and replay for reviews",
    ],
  },
  "Voice AI": {
    title: "Voice AI",
    subtitle: "Natural, low-latency conversations",
    items: [
      "Streaming STT/TTS with turn-taking",
      "Tool use during calls",
      "Brand-safe voices and fallbacks",
      "Noise-aware UX patterns",
    ],
  },
  Automation: {
    title: "Automation",
    subtitle: "From answers to completed work",
    items: [
      "Triggers, schedules, and queues",
      "Human-in-the-loop approvals",
      "Repeatable playbooks across teams",
      "Metrics on resolution and handoff",
    ],
  },
};

export function InfoPanel({ section, onClose }: InfoPanelProps) {
  const content = section ? sections[section] : null;

  if (!content) return null;

  return (
    <motion.div
      className="relative z-[12] w-full max-w-[560px] mx-auto px-4"
      initial={{ opacity: 0, y: 12, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      exit={{ opacity: 0, y: -8, filter: "blur(4px)" }}
      transition={{ duration: 0.32, ease: [0.32, 0.72, 0, 1] }}
    >
      <div
        className="rounded-2xl border px-5 py-5 shadow-[0_24px_80px_-24px_rgba(0,0,0,0.85)]"
        style={{
          background: "rgba(10, 11, 16, 0.72)",
          borderColor: "rgba(255,255,255,0.06)",
          backdropFilter: "blur(20px)",
        }}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 className="text-base font-semibold tracking-tight" style={{ color: "rgba(232,234,240,0.95)" }}>
              {content.title}
            </h2>
            <p className="text-sm mt-1 font-light" style={{ color: "rgba(160,168,192,0.75)" }}>
              {content.subtitle}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 text-xs px-3 py-1.5 rounded-full transition-colors duration-200"
            style={{
              color: "rgba(232,234,240,0.65)",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
            aria-label="Закрыть панель"
          >
            Закрыть
          </button>
        </div>

        <ul className="space-y-2.5">
          {content.items.map((item, idx) => (
            <motion.li
              key={item}
              className="flex items-start gap-3 text-sm leading-relaxed"
              style={{ color: "rgba(232,234,240,0.82)" }}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.04 * idx, duration: 0.28 }}
            >
              <span
                className="flex-shrink-0 w-1 h-1 rounded-full mt-2"
                style={{ background: "rgba(124, 92, 200, 0.55)" }}
              />
              <span>{item}</span>
            </motion.li>
          ))}
        </ul>
      </div>
    </motion.div>
  );
}
