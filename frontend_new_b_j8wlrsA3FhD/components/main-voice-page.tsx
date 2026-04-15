// ══════════════════════════════════════════════════════════════════════════════
// DZEN.AI VOICE INTERFACE — Main Page
// ══════════════════════════════════════════════════════════════════════════════
// 
// This is the core voice-first UI for Dzen.AI. The layout is minimal and focused:
//
// Layer Structure (z-index):
//   z-0:   LiquidEther background (fluid simulation)
//   z-10:  Main content (sphere, transcript, etc.)
//   z-15:  InfoPanel (when open)
//   z-20:  TopBar (navigation header)
//   z-50:  Dev controls (development only)
//
// State Flow:
//   1. activeBentoSection: Controls which info panel is open (Platform/Use Cases/How It Works)
//   2. callStatus: Call lifecycle state (idle → connecting → in-call → ended)
//   3. isVideoOpen: Whether video overlay is visible
//
// ══════════════════════════════════════════════════════════════════════════════

"use client";

import { AnimatePresence, motion } from "framer-motion";
import { memo, useCallback, useState } from "react";
import LiquidEther from "@/components/liquid-ether";
import { TopBar } from "@/components/top-bar";
import { InfoPanel } from "@/components/info-panel";
import { VoiceSphere } from "@/components/voice-sphere";
import { VoiceTranscriptHistory } from "@/components/voice-transcript-history";
import { SpeakerIndicator } from "@/components/speaker-indicator";
import { VideoOverlayPlayer } from "@/components/video-overlay-player";
import { useVapiCall } from "@/hooks/use-vapi-call";
import type { TranscriptProbe } from "@/hooks/use-vapi-call";
import { useMediaOverlay } from "@/hooks/use-media-overlay";

// Stable reference to avoid WebGL re-init on each transcript chunk update.
const LIQUID_COLORS = ["#05060A", "#7C3AED", "#22D3EE"] as const;

const BackgroundLayer = memo(function BackgroundLayer() {
  return (
    <div className="fixed inset-0 z-0" style={{ height: "100vh" }}>
      <LiquidEther
        colors={LIQUID_COLORS as unknown as string[]}
        mouseForce={12}
        cursorSize={100}
        isViscous={false}
        resolution={0.5}
        autoDemo={true}
        autoSpeed={0.3}
        autoIntensity={1.5}
        autoResumeDelay={3000}
      />
    </div>
  );
});

export function MainVoicePage() {
  // ─────────────────────────────────────────────────────────────────────────
  // STATE MANAGEMENT
  // ─────────────────────────────────────────────────────────────────────────
  
  // Which info section is currently open: null | 'Platform' | 'Use Cases' | 'How It Works'
  const [activeBentoSection, setActiveBentoSection] = useState<string | null>(null);

  // ─────────────────────────────────────────────────────────────────────────
  // HOOKS: Video Overlay & Vapi Call Management
  // ─────────────────────────────────────────────────────────────────────────
  
  // Video overlay state: isOpen, activeVideo, show/hide callbacks
  // Used when agent calls tool_use.show_video(videoId)
  const { mediaState, showVideo, hideVideo } = useMediaOverlay();

  // [Vapi Integration Point]
  // Manages entire voice call lifecycle: connect, transcripts, tool-calls
  // Required env vars: NEXT_PUBLIC_VAPI_PUBLIC_KEY, NEXT_PUBLIC_VAPI_ASSISTANT_ID
  // See hooks/use-vapi-call.ts for integration details
  const { uiState, turns, transcriptLogs, showDebugLogs, clearTranscriptLogs, toggleCall } = useVapiCall({
    onShowVideo: showVideo,  // Called when agent executes show_video tool
    onHideVideo: hideVideo,  // Called when agent executes hide_video tool
  });

  // Destructure state
  const { isVideoOpen, activeVideo } = mediaState;
  const { callStatus, errorMessage, activeSpeaker } = uiState;

  // UI visibility logic
  const showTranscript =
    callStatus === "in-call" ||
    callStatus === "ended" ||
    (callStatus === "idle" && turns.length > 0);

  const isIdle = callStatus === "idle";

  return (
    <main
      className="relative flex flex-col items-center min-h-dvh overflow-x-hidden"
      style={{ background: "#05060A" }}
    >
      {/*
        Flicker fix: keep background node isolated and memoized.
        Transcript streaming updates must not recreate WebGL background.
      */}
      <BackgroundLayer />

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* LAYER 20: Top Navigation Bar                                        */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 
        Fixed header with Dzen.AI branding and nav links (Platform, Use Cases,
        How It Works). Active section shown with subtle violet underline.
        Click → opens corresponding InfoPanel below sphere.
      */}
      <TopBar onNavClick={setActiveBentoSection} activeSection={activeBentoSection} />

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* LAYER 15: Info Panel — Contextual Content Layer                    */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 
        Appears when user clicks TopBar items. Each section shows different
        content (Platform features, Use Cases, How It Works architecture).
        Has explicit "Close" button to return to main mode.
        Animates in/out smoothly, mode="wait" prevents animation conflicts.
      */}
      <AnimatePresence mode="wait">
        {activeBentoSection && (
          <InfoPanel section={activeBentoSection} onClose={() => setActiveBentoSection(null)} />
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* LAYER 10: Main Content Column — Centered Voice Interface            */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      <div className="relative z-10 flex flex-col items-center w-full max-w-xl mx-auto px-4 pt-16 pb-10 gap-6">

        {/* ─────────────────────────────────────────────────────────────── */}
        {/* VOICE SPHERE SECTION — Primary Interactive Element              */}
        {/* ─────────────────────────────────────────────────────────────── */}
        <section className="flex flex-col items-center gap-4 w-full">
          <VoiceSphere
            uiState={uiState}
            isVideoOpen={isVideoOpen}
            onClick={toggleCall}
          />

          {/* Speaker indicator — only during call */}
          <AnimatePresence>
            {callStatus === "in-call" && (
              <motion.div
                key="speaker"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.25 }}
              >
                <SpeakerIndicator uiState={uiState} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Tap prompt — idle only, no text during call */}
          <AnimatePresence>
            {isIdle && (
              <motion.p
                key="prompt"
                className="text-sm font-light tracking-wide text-center"
                style={{ color: "rgba(232,234,240,0.35)" }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.4 }}
              >
                Нажмите, чтобы говорить
              </motion.p>
            )}
          </AnimatePresence>

          {/* Connecting label */}
          <AnimatePresence>
            {callStatus === "connecting" && (
              <motion.div
                key="connecting"
                className="flex items-center gap-2"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
              >
                <ConnectingDots />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Error message — minimal single-line */}
          <AnimatePresence>
            {callStatus === "error" && errorMessage && (
              <motion.p
                key="error"
                className="text-xs text-center px-4 py-1.5 rounded-full"
                style={{
                  color: "rgba(251,113,133,0.9)",
                  background: "rgba(251,113,133,0.08)",
                  border: "1px solid rgba(251,113,133,0.2)",
                }}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.25 }}
                role="alert"
              >
                {errorMessage}
              </motion.p>
            )}
          </AnimatePresence>
        </section>

        {/* ── Video overlay ─────────────────────────────────────────── */}
        <VideoOverlayPlayer
          video={activeVideo}
          isOpen={isVideoOpen}
          onClose={hideVideo}
        />

        {/* ── Transcript history ────────────────────────────────────── */}
        {/*
          Keep transcript node stable during streaming updates.
          Removing AnimatePresence here avoids remount/replay effects that can
          cause visible flicker while partial chunks arrive.
        */}
        {showTranscript && (
          <VoiceTranscriptHistory turns={turns} isVisible={showTranscript} />
        )}

        {showDebugLogs && <TranscriptDebugPanel logs={transcriptLogs} onClear={clearTranscriptLogs} />}
      </div>

      {/* ── Dev-only demo controls — hidden in production ─────────────── */}
      {process.env.NODE_ENV === "development" && (
        <DemoControls onShowVideo={() => showVideo("demo-002")} onHideVideo={hideVideo} />
      )}
    </main>
  );
}

function TranscriptDebugPanel({
  logs,
  onClear,
}: {
  logs: TranscriptProbe[];
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);

  const copyLogs = useCallback(async () => {
    const payload = logs.map(({ seq, ts, source, eventType, role, status, transcriptType, transcript, raw }) => ({
      seq,
      ts,
      source,
      eventType,
      role,
      status,
      transcriptType,
      transcript,
      raw,
    }));
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    } catch {
      // noop: clipboard can be blocked by browser permissions.
    }
  }, [logs]);

  return (
    <section className="w-full max-w-[560px] mx-auto px-4">
      <div
        className="rounded-[16px] border px-3 py-2"
        style={{
          background: "rgba(16,18,26,0.72)",
          borderColor: "rgba(255,255,255,0.08)",
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <button
            onClick={() => setOpen((v) => !v)}
            className="text-xs px-2 py-1 rounded-full"
            style={{
              color: "rgba(232,234,240,0.9)",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            {open ? "Скрыть логи VAPI" : "Показать логи VAPI"}
          </button>

          <div className="flex items-center gap-2">
            <span className="text-[11px]" style={{ color: "rgba(232,234,240,0.55)" }}>
              {logs.length} событий
            </span>
            <button
              onClick={copyLogs}
              className="text-[11px] px-2 py-1 rounded-full"
              style={{
                color: "#22D3EE",
                background: "rgba(34,211,238,0.08)",
                border: "1px solid rgba(34,211,238,0.2)",
              }}
            >
              Скопировать JSON
            </button>
            <button
              onClick={onClear}
              className="text-[11px] px-2 py-1 rounded-full"
              style={{
                color: "rgba(232,234,240,0.75)",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              Очистить
            </button>
          </div>
        </div>

        {open && (
          <div
            className="mt-2 rounded-xl border overflow-auto"
            style={{
              maxHeight: 180,
              borderColor: "rgba(255,255,255,0.08)",
              background: "rgba(5,6,10,0.6)",
            }}
          >
            <pre className="text-[10px] leading-relaxed p-2 whitespace-pre-wrap break-words text-white/80">
              {JSON.stringify(
                logs.map(({ seq, ts, source, eventType, role, status, transcriptType, transcript, raw }) => ({
                  seq,
                  ts,
                  source,
                  eventType,
                  role,
                  status,
                  transcriptType,
                  transcript,
                  raw,
                })),
                null,
                2
              )}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
}

// ── Connecting dots animation ──────────────────────────────────────────────

function ConnectingDots() {
  return (
    <div className="flex items-center gap-1.5" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="rounded-full"
          style={{ width: 4, height: 4, background: "rgba(124,58,237,0.6)" }}
          animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
          transition={{
            duration: 1.2,
            repeat: Infinity,
            ease: "easeInOut",
            delay: i * 0.2,
          }}
        />
      ))}
    </div>
  );
}

// ── Dev-only demo controls ─────────────────────────────────────────────────

function DemoControls({
  onShowVideo,
  onHideVideo,
}: {
  onShowVideo: () => void;
  onHideVideo: () => void;
}) {
  return (
    <div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-2 rounded-2xl z-50"
      style={{
        background: "rgba(12,13,20,0.9)",
        border: "1px solid rgba(255,255,255,0.06)",
        backdropFilter: "blur(12px)",
      }}
    >
      <span
        className="text-[9px] tracking-widest font-mono mr-1"
        style={{ color: "rgba(255,255,255,0.2)" }}
      >
        DEV
      </span>
      <button
        onClick={onShowVideo}
        className="text-[10px] px-2 py-0.5 rounded-full"
        style={{
          color: "#22D3EE",
          background: "rgba(34,211,238,0.08)",
          border: "1px solid rgba(34,211,238,0.2)",
        }}
      >
        show video
      </button>
      <button
        onClick={onHideVideo}
        className="text-[10px] px-2 py-0.5 rounded-full"
        style={{
          color: "rgba(232,234,240,0.4)",
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        hide video
      </button>
    </div>
  );
}
