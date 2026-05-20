"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useState } from "react";
import { AmbientBackground } from "@/components/ambient-background";
import { TopBar } from "@/components/top-bar";
import { InfoPanel } from "@/components/info-panel";
import { VoiceSphere } from "@/components/voice-sphere";
import { VoiceTranscriptHistory } from "@/components/voice-transcript-history";
import { SpeakerIndicator } from "@/components/speaker-indicator";
import { MagicBento } from "@/components/magic-bento";
import { VapiDebugConsole } from "@/components/vapi-debug-console";
import { useVapiCall } from "@/hooks/use-vapi-call";
import type { TranscriptProbe } from "@/hooks/use-vapi-call";

export function MainVoicePage() {
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const { uiState, messages, transcriptLogs, showDebugLogs, clearTranscriptLogs, toggleCall } = useVapiCall();
  const { callStatus, errorMessage } = uiState;

  const isIdle = callStatus === "idle";

  const onBentoOrNav = useCallback((title: string) => {
    setActiveSection((prev) => (prev === title ? null : title));
  }, []);

  return (
    <main className="relative min-h-dvh overflow-x-hidden text-[rgba(232,234,240,0.92)]">
      <AmbientBackground />

      <TopBar onNavClick={onBentoOrNav} activeSection={activeSection} />

      <div className="relative z-10 mx-auto flex w-full max-w-6xl flex-col items-center px-4 pb-20 pt-[5.5rem] md:px-8">
        <section className="flex w-full flex-col items-center gap-5 md:gap-6">
          <motion.div
            className="flex flex-col items-center gap-3"
            animate={{ y: activeSection ? -8 : 0 }}
            transition={{ duration: 0.38, ease: [0.32, 0.72, 0, 1] }}
          >
            <VoiceSphere
              uiState={uiState}
              isVideoOpen={false}
              onClick={toggleCall}
              compact={!!activeSection}
            />

            <AnimatePresence mode="wait">
              {callStatus === "in-call" && (
                <motion.div
                  key="speaker"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.28 }}
                >
                  <SpeakerIndicator uiState={uiState} />
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence mode="wait">
              {isIdle && (
                <motion.p
                  key="hint"
                  className="text-center text-sm font-light text-[rgba(160,168,192,0.42)]"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.35 }}
                >
                  Нажмите на сферу, чтобы говорить
                </motion.p>
              )}
              {callStatus === "connecting" && (
                <motion.div
                  key="conn"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center gap-2"
                >
                  <ConnectingDots />
                </motion.div>
              )}
              {callStatus === "error" && errorMessage && (
                <motion.p
                  key="err"
                  role="alert"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="max-w-md rounded-full border px-4 py-1.5 text-center text-xs"
                  style={{
                    color: "rgba(251,160,170,0.95)",
                    borderColor: "rgba(251,113,133,0.25)",
                    background: "rgba(251,113,133,0.06)",
                  }}
                >
                  {errorMessage}
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>

          <AnimatePresence mode="wait">
            {activeSection && (
              <InfoPanel key={activeSection} section={activeSection} onClose={() => setActiveSection(null)} />
            )}
          </AnimatePresence>

          <div className="w-full max-w-[500px]">
            <VoiceTranscriptHistory messages={messages} />
          </div>
        </section>

        <motion.section
          className="mt-14 w-full md:mt-20"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.12, ease: [0.32, 0.72, 0, 1] }}
        >
          <h2 className="mb-6 text-center text-xs font-medium uppercase tracking-[0.2em] text-[rgba(140,150,180,0.45)]">
            Продукт
          </h2>
          <MagicBento
            enableTilt={false}
            enableMagnetism
            particleCount={10}
            glowColor="100, 85, 160"
            onCardClick={onBentoOrNav}
          />
        </motion.section>

        {showDebugLogs && (
          <div className="mt-10 w-full max-w-[500px]">
            <TranscriptDebugPanel logs={transcriptLogs} onClear={clearTranscriptLogs} />
          </div>
        )}
      </div>

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
  return <VapiDebugConsole logs={logs} onClear={onClear} />;
}

function ConnectingDots() {
  return (
    <div className="flex items-center gap-1.5" aria-hidden>
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="h-1 w-1 rounded-full bg-[rgba(120,90,180,0.55)]"
          animate={{ opacity: [0.35, 1, 0.35], scale: [0.85, 1.15, 0.85] }}
          transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut", delay: i * 0.18 }}
        />
      ))}
    </div>
  );
}

