// ══════════════════════════════════════════════════════════════════════════════
// VOICE SPHERE COMPONENT — Central Interactive Element
// ══════════════════════════════════════════════════════════════════════════════
//
// This is the PRIMARY UI for the entire interface. It's a 3D WebGL-rendered sphere
// (Orb component) that responds to call state and speaker changes.
//
// STATE-BASED BEHAVIOR:
//   idle/ended:  Violet hue, breathing pulse, idle prompt shown
//   connecting:  Violet hue + pulsing outer ring
//   in-call:     Dynamic hue (cyan assistant, purple user), glowing pulse
//
// INTERACTION:
//   Click → toggleCall() in parent (start/stop voice session)
//   Scales down 50% when video overlay opens
//   Smooth scale animation (0.6s duration)
//
// ══════════════════════════════════════════════════════════════════════════════

"use client";

import { motion } from "framer-motion";
import Orb from "@/components/orb";
import type { UiState } from "@/types/voice";

interface VoiceSphereProps {
  uiState: UiState;
  isVideoOpen: boolean;
  onClick: () => void;
}

export function VoiceSphere({ uiState, isVideoOpen, onClick }: VoiceSphereProps) {
  const { callStatus, activeSpeaker } = uiState;

  const isIdle = callStatus === "idle" || callStatus === "ended";
  const isConnecting = callStatus === "connecting";
  const isInCall = callStatus === "in-call";
  const isSpeaking = isInCall && activeSpeaker !== null;

  // Hue shift based on speaker — violet idle, cyan assistant, purple user
  const hue = 
    activeSpeaker === "assistant" ? 180 
    : activeSpeaker === "user" ? 280
    : 260;

  // Hover intensity increases during call
  const hoverIntensity = isSpeaking ? 0.3 : isInCall ? 0.2 : 0.15;

  // Always rotate in call, force hover when speaking
  const forceHoverState = isSpeaking;

  return (
    <motion.div
      className="relative flex items-center justify-center"
      animate={{
        scale: isVideoOpen ? 0.5 : 1,
      }}
      transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
      style={{
        width: isVideoOpen ? 120 : 240,
        height: isVideoOpen ? 120 : 240,
      }}
    >
      {/* Outer glow ring — pulsing, sits behind orb */}
      <motion.div
        className="absolute rounded-full pointer-events-none"
        style={{
          width: "100%",
          height: "100%",
          background: "radial-gradient(circle, rgba(124,58,237,0.2) 0%, transparent 70%)",
        }}
        animate={
          isSpeaking
            ? { opacity: [0.5, 0.9, 0.5], scale: [0.95, 1.1, 0.95] }
            : isConnecting
            ? { opacity: [0.2, 0.6, 0.2], scale: [0.98, 1.05, 0.98] }
            : { opacity: [0.2, 0.4, 0.2], scale: [0.97, 1.02, 0.97] }
        }
        transition={{
          duration: isSpeaking ? 0.8 : 3.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Orb canvas — the core visual */}
      <motion.button
        onClick={onClick}
        aria-label={
          isIdle
            ? "Начать голосовой разговор"
            : isConnecting
            ? "Подключение..."
            : "Завершить разговор"
        }
        className="relative rounded-full cursor-pointer select-none outline-none focus-visible:ring-2 focus-visible:ring-[#7C3AED] focus-visible:ring-offset-4 focus-visible:ring-offset-[#05060A] overflow-hidden"
        style={{
          width: "100%",
          height: "100%",
        }}
        whileTap={{ scale: 0.94 }}
        whileHover={isIdle ? { scale: 1.05 } : {}}
      >
        <Orb
          hue={hue}
          hoverIntensity={hoverIntensity}
          rotateOnHover={isInCall}
          forceHoverState={forceHoverState}
          backgroundColor="#05060A"
        />
      </motion.button>

      {/* Connecting pulsing ring */}
      {isConnecting && (
        <motion.div
          className="absolute inset-0 rounded-full pointer-events-none"
          style={{
            border: "2px solid rgba(124,58,237,0.4)",
          }}
          animate={{ scale: [1, 1.5, 2], opacity: [0.8, 0.3, 0] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: "easeOut" }}
        />
      )}
    </motion.div>
  );
}


