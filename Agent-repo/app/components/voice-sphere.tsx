"use client";

import { motion } from "framer-motion";
import Orb from "@/components/orb";
import type { UiState } from "@/types/voice";

interface VoiceSphereProps {
  uiState: UiState;
  isVideoOpen: boolean;
  onClick: () => void;
  /** When a nav/info panel is open — hero compresses upward */
  compact?: boolean;
}

export function VoiceSphere({ uiState, isVideoOpen, onClick, compact }: VoiceSphereProps) {
  const { callStatus, activeSpeaker } = uiState;

  const isIdle = callStatus === "idle" || callStatus === "ended";
  const isConnecting = callStatus === "connecting";
  const isInCall = callStatus === "in-call";
  const isSpeaking = isInCall && activeSpeaker !== null;

  const hue =
    activeSpeaker === "assistant" ? 185 : activeSpeaker === "user" ? 275 : 262;

  const hoverIntensity = isSpeaking ? 0.32 : isInCall ? 0.22 : 0.14;
  const forceHoverState = isSpeaking;

  const baseSize = isVideoOpen ? 120 : compact ? 200 : 228;

  return (
    <motion.div
      className="relative flex items-center justify-center"
      animate={{
        scale: isVideoOpen ? 0.52 : 1,
        y: compact ? -10 : 0,
      }}
      transition={{ duration: 0.45, ease: [0.32, 0.72, 0, 1] }}
      style={{ width: baseSize, height: baseSize }}
    >
      {/* Idle breathing + assistant pulse + user micro-motion */}
      <motion.div
        className="absolute flex items-center justify-center rounded-full"
        style={{ width: "100%", height: "100%" }}
        animate={
          isIdle && !isVideoOpen
            ? { scale: [1, 1.035, 1] }
            : activeSpeaker === "assistant"
              ? { scale: [1, 1.07, 1] }
              : activeSpeaker === "user"
                ? {
                    x: [0, -2, 2, -1.5, 1.5, 0],
                    y: [0, 1.5, -1, 1, 0],
                  }
                : { scale: 1, x: 0, y: 0 }
        }
        transition={
          isIdle && !isVideoOpen
            ? { duration: 5.5, repeat: Infinity, ease: "easeInOut" }
            : activeSpeaker === "assistant"
              ? { duration: 1.15, repeat: Infinity, ease: "easeInOut" }
              : activeSpeaker === "user"
                ? { duration: 0.45, repeat: Infinity, ease: "linear" }
                : { duration: 0.3 }
        }
      >
        <motion.div
          className="absolute rounded-full pointer-events-none"
          style={{
            width: "108%",
            height: "108%",
            left: "-4%",
            top: "-4%",
            background:
              "radial-gradient(circle, rgba(100,80,160,0.18) 0%, rgba(40,60,90,0.08) 45%, transparent 72%)",
          }}
          animate={
            isSpeaking
              ? { opacity: [0.35, 0.75, 0.35], scale: [0.96, 1.08, 0.96] }
              : isConnecting
                ? { opacity: [0.2, 0.5, 0.2], scale: [0.98, 1.04, 0.98] }
                : { opacity: [0.2, 0.38, 0.2], scale: [0.97, 1.03, 0.97] }
          }
          transition={{
            duration: isSpeaking ? 0.85 : isConnecting ? 1.4 : 4.2,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />

        <motion.button
          type="button"
          onClick={onClick}
          aria-label={
            isIdle
              ? "Начать голосовой разговор"
              : isConnecting
                ? "Подключение..."
                : "Завершить разговор"
          }
          className="relative z-[1] h-full w-full cursor-pointer select-none overflow-hidden rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[rgba(124,92,200,0.55)] focus-visible:ring-offset-2 focus-visible:ring-offset-[#05070A]"
          whileTap={{ scale: 0.96 }}
          whileHover={isIdle && !isVideoOpen ? { scale: 1.04 } : {}}
        >
          <Orb
            hue={hue}
            hoverIntensity={hoverIntensity}
            rotateOnHover={isInCall}
            forceHoverState={forceHoverState}
            backgroundColor="#05070A"
          />
        </motion.button>

        {isConnecting && (
          <motion.div
            className="pointer-events-none absolute inset-0 rounded-full"
            style={{ border: "1px solid rgba(124,92,200,0.35)" }}
            animate={{ scale: [1, 1.45, 1.9], opacity: [0.65, 0.2, 0] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
          />
        )}
      </motion.div>
    </motion.div>
  );
}
