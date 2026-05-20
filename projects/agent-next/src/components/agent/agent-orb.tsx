"use client";

import { motion } from "framer-motion";
import type { AgentOrbVisualState } from "@/components/agent/types";

type AgentOrbProps = {
  state: AgentOrbVisualState;
  open: boolean;
  onToggle: () => void;
};

const stateClassMap: Record<AgentOrbVisualState, string> = {
  idle: "shadow-[0_0_72px_rgba(231,197,154,0.2)]",
  hover: "shadow-[0_0_104px_rgba(231,197,154,0.32)]",
  listening: "shadow-[0_0_120px_rgba(231,197,154,0.38)]",
  thinking: "shadow-[0_0_98px_rgba(231,197,154,0.28)]",
  speaking: "shadow-[0_0_132px_rgba(231,197,154,0.46)]",
  error: "shadow-[0_0_84px_rgba(111,75,75,0.34)]",
};

const animationMap: Record<AgentOrbVisualState, { scale: number[]; rotate: number[]; opacity: number[] }> = {
  idle: { scale: [1, 1.018, 1], rotate: [0, 0], opacity: [0.9, 0.95, 0.9] },
  hover: { scale: [1.03, 1.06, 1.03], rotate: [0, 0], opacity: [0.97, 1, 0.97] },
  listening: { scale: [1, 1.04, 1], rotate: [0, 0], opacity: [0.95, 1, 0.95] },
  thinking: { scale: [1, 1.03, 1], rotate: [0, 72, 144, 216, 288, 360], opacity: [0.92, 0.98, 0.92] },
  speaking: { scale: [1, 1.07, 0.99, 1.055, 1], rotate: [0, 0], opacity: [1, 0.93, 1, 0.93, 1] },
  error: { scale: [1, 0.985, 1], rotate: [0, 0], opacity: [0.8, 0.74, 0.8] },
};

export function AgentOrb({ state, open, onToggle }: AgentOrbProps) {
  const sizeClass = open ? "h-56 w-56 md:h-[17rem] md:w-[17rem]" : "h-80 w-80 md:h-[23rem] md:w-[23rem]";
  const animation = animationMap[state];
  const coreGlowClass =
    state === "speaking"
      ? "opacity-100"
      : state === "thinking"
        ? "opacity-90"
        : state === "listening"
          ? "opacity-85"
          : "opacity-75";

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label="Открыть панель агента"
      className="group relative flex items-center justify-center"
    >
      <motion.div
        className={`relative ${sizeClass} rounded-full border border-[rgba(255,255,255,0.18)] bg-[radial-gradient(circle_at_32%_26%,rgba(255,255,255,0.34),rgba(222,194,150,0.2)_20%,rgba(18,18,24,0.44)_56%,rgba(9,10,14,0.82)_100%)] ${stateClassMap[state]}`}
        animate={animation}
        transition={{
          duration: state === "speaking" ? 1.25 : state === "thinking" ? 4.8 : 3.2,
          repeat: Number.POSITIVE_INFINITY,
          ease: "easeInOut",
        }}
      >
        <div className="pointer-events-none absolute inset-4 rounded-full border border-white/18" />
        <div className="pointer-events-none absolute inset-7 rounded-full border border-[rgba(231,197,154,0.26)]" />
        <div
          className={`pointer-events-none absolute inset-[26%] rounded-full bg-[radial-gradient(circle_at_44%_38%,rgba(255,255,255,0.92),rgba(235,208,165,0.78)_28%,rgba(231,197,154,0.34)_52%,rgba(19,20,28,0)_74%)] blur-[1.1px] transition-opacity duration-700 ${coreGlowClass}`}
        />
        <div className="pointer-events-none absolute inset-[14%] rounded-full border border-[rgba(255,255,255,0.1)]" />
        <div className="pointer-events-none absolute inset-[17%] rounded-full border border-[rgba(231,197,154,0.2)]" />
        <motion.div
          className="pointer-events-none absolute inset-[6%] rounded-full border border-[rgba(255,255,255,0.14)]"
          animate={{ rotate: [0, 360] }}
          transition={{ duration: state === "thinking" ? 11 : 17, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
        />
        <motion.div
          className="pointer-events-none absolute inset-[9%] rounded-full border border-[rgba(231,197,154,0.18)]"
          animate={{ rotate: [360, 0] }}
          transition={{ duration: state === "speaking" ? 10 : 14, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
        />
        <div className="pointer-events-none absolute inset-[9%] rounded-full bg-[radial-gradient(circle_at_35%_22%,rgba(255,255,255,0.16),rgba(255,255,255,0)_48%)]" />
        <motion.div
          className="pointer-events-none absolute -inset-2 rounded-full bg-[radial-gradient(circle,rgba(231,197,154,0.24),rgba(231,197,154,0)_68%)] blur-lg"
          animate={{ opacity: state === "speaking" ? [0.6, 0.95, 0.62] : state === "listening" ? [0.48, 0.78, 0.5] : [0.4, 0.62, 0.42] }}
          transition={{ duration: state === "speaking" ? 1.35 : 2.4, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
        />
      </motion.div>
    </button>
  );
}
