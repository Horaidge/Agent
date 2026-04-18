"use client";

import { motion, AnimatePresence } from "framer-motion";
import type { UiState } from "@/types/voice";

interface SpeakerIndicatorProps {
  uiState: UiState;
}

export function SpeakerIndicator({ uiState }: SpeakerIndicatorProps) {
  const { callStatus, activeSpeaker } = uiState;

  if (callStatus !== "in-call") return null;

  return (
    <div
      className="flex items-center gap-3"
      aria-live="polite"
      aria-atomic="true"
      aria-label={
        activeSpeaker === "user"
          ? "Вы говорите"
          : activeSpeaker === "assistant"
          ? "Агент говорит"
          : "Ожидание"
      }
    >
      {/* YOU chip */}
      <SpeakerChip label="YOU" isActive={activeSpeaker === "user"} color="#A78BFA" />

      {/* AI chip */}
      <SpeakerChip label="AI" isActive={activeSpeaker === "assistant"} color="#22D3EE" />
    </div>
  );
}

interface SpeakerChipProps {
  label: string;
  isActive: boolean;
  color: string;
}

function SpeakerChip({ label, isActive, color }: SpeakerChipProps) {
  return (
    <motion.div
      className="relative flex items-center gap-1.5 px-2.5 py-1 rounded-full"
      animate={{
        backgroundColor: isActive ? `${color}18` : "transparent",
        borderColor: isActive ? `${color}60` : "rgba(255,255,255,0.08)",
      }}
      transition={{ duration: 0.25 }}
      style={{
        border: "1px solid",
        borderColor: isActive ? `${color}60` : "rgba(255,255,255,0.08)",
      }}
    >
      {/* Active pulse dot */}
      <AnimatePresence>
        {isActive && (
          <motion.span
            key="dot"
            className="relative flex"
            style={{ width: 6, height: 6 }}
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.5 }}
            transition={{ duration: 0.2 }}
          >
            {/* Ping */}
            <motion.span
              className="absolute inset-0 rounded-full"
              style={{ backgroundColor: color }}
              animate={{ scale: [1, 1.8, 1], opacity: [0.8, 0, 0.8] }}
              transition={{ duration: 1.2, repeat: Infinity, ease: "easeOut" }}
            />
            <span
              className="relative rounded-full"
              style={{ width: 6, height: 6, backgroundColor: color }}
            />
          </motion.span>
        )}
      </AnimatePresence>

      <span
        className="text-[10px] font-semibold tracking-widest leading-none"
        style={{
          color: isActive ? color : "rgba(255,255,255,0.25)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {label}
      </span>
    </motion.div>
  );
}
