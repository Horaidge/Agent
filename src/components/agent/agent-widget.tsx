"use client";

import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { ChatPanelTransition } from "@/components/animations/chat-panel-transition";
import Threads from "@/components/animations/threads";
import { AgentChatPanel } from "@/components/agent/agent-chat-panel";
import { AgentOrb } from "@/components/agent/agent-orb";
import {
  AGENT_ORB_STATE_PRIORITY,
  type AgentOrbVisualState,
  type AgentRuntimeAdapter,
  type AgentSessionState,
} from "@/components/agent/types";

const AGENT_THREADS_RGB: [number, number, number] = [0.91, 0.78, 0.62];

type AgentWidgetProps = {
  className?: string;
  runtime?: AgentRuntimeAdapter;
};

const mockSession: AgentSessionState = {
  status: "idle",
  messages: [
    {
      id: "a1",
      role: "assistant",
      content: "Привет. Я готов показать сценарий взаимодействия Hyperstudio.",
      timestamp: new Date().toISOString(),
    },
  ],
  tools: [
    { id: "t1", name: "context-lookup", status: "done", summary: "Выбран набор материалов для демо." },
    { id: "t2", name: "response-plan", status: "running", summary: "Готовится структура следующего шага." },
  ],
};

function useMockRuntime(): AgentRuntimeAdapter {
  const [session, setSession] = useState<AgentSessionState>(mockSession);

  return useMemo(
    () => ({
      session,
      openSession: () => setSession((s) => ({ ...s, status: s.status === "error" ? "idle" : "listening" })),
      closeSession: () => setSession((s) => ({ ...s, status: "idle" })),
      setStatus: (status) => setSession((s) => ({ ...s, status })),
      sendMessage: (text: string) =>
        setSession((s) => ({
          ...s,
          status: "thinking",
          messages: [
            ...s.messages,
            { id: crypto.randomUUID(), role: "user", content: text, timestamp: new Date().toISOString() },
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: "Mock-ответ. На следующем этапе это сообщение придет из текущего VAPI pipeline.",
              timestamp: new Date().toISOString(),
            },
          ],
        })),
    }),
    [session],
  );
}

function resolveOrbState(sessionStatus: AgentSessionState["status"], isHover: boolean): AgentOrbVisualState {
  const requestedState: AgentOrbVisualState =
    sessionStatus === "error"
      ? "error"
      : sessionStatus === "speaking"
        ? "speaking"
        : sessionStatus === "thinking"
          ? "thinking"
          : sessionStatus === "listening"
            ? "listening"
            : isHover
              ? "hover"
              : "idle";

  return AGENT_ORB_STATE_PRIORITY.find((state) => state === requestedState) ?? "idle";
}

export function AgentWidget({ className = "", runtime }: AgentWidgetProps) {
  const mockRuntime = useMockRuntime();
  const activeRuntime = runtime ?? mockRuntime;

  const [chatOpen, setChatOpen] = useState(false);
  const [isHover, setIsHover] = useState(false);
  const orbState = resolveOrbState(activeRuntime.session.status, isHover);
  const dockOrb = chatOpen;
  const activeSpeaker = activeRuntime.session.activeSpeaker ?? null;

  const sceneState = useMemo<"calm" | "attention" | "thinking">(() => {
    if (activeRuntime.session.status === "thinking") return "thinking";
    if (activeRuntime.session.status === "listening" || activeRuntime.session.status === "speaking") {
      return "attention";
    }
    return "calm";
  }, [activeRuntime.session.status]);

  const threadsPreset = useMemo(() => {
    switch (sceneState) {
      case "attention":
        return {
          amplitude: 1.9,
          distance: 0.68,
          flow: 0.73,
          pulse: 0.068,
          complexity: 0.98,
          orbInfluence: 0.29,
          orbWarp: 0.09,
          orbRadius: 0.2,
        };
      case "thinking":
        return {
          amplitude: 1.96,
          distance: 0.7,
          flow: 0.77,
          pulse: 0.078,
          complexity: 1.02,
          orbInfluence: 0.32,
          orbWarp: 0.11,
          orbRadius: 0.22,
        };
      default:
        return {
          amplitude: 1.82,
          distance: 0.66,
          flow: 0.68,
          pulse: 0.055,
          complexity: 0.93,
          orbInfluence: 0.27,
          orbWarp: 0.12,
          orbRadius: 0.19,
        };
    }
  }, [sceneState]);

  const orbAuraOpacity = orbState === "speaking" ? 0.48 : orbState === "thinking" ? 0.42 : orbState === "listening" ? 0.36 : 0.3;

  const handleOrbToggle = () => {
    const nextOpen = !chatOpen;
    setChatOpen(nextOpen);
    if (nextOpen) activeRuntime.openSession();
    if (!nextOpen) activeRuntime.closeSession();
  };

  const listeningBoost = activeRuntime.session.status === "listening" ? 0.022 : 0;
  const speakingBoost = activeRuntime.session.status === "speaking" ? 0.038 : 0;
  const thinkingBoost = activeRuntime.session.status === "thinking" ? 0.01 : 0;
  const speakerBoost = activeSpeaker === "assistant" ? 0.042 : activeSpeaker === "user" ? 0.032 : 0;
  const effectiveFlow = Math.min(0.93, threadsPreset.flow + listeningBoost + speakingBoost + thinkingBoost + speakerBoost);
  const effectivePulse = Math.min(
    0.135,
    threadsPreset.pulse +
      listeningBoost * 0.34 +
      speakingBoost * 0.45 +
      thinkingBoost * 0.2 +
      speakerBoost * 0.42,
  );

  const statusText =
    activeRuntime.session.status === "speaking"
      ? "Отвечаю и сопровождаю ваш запрос"
      : activeRuntime.session.status === "thinking"
        ? "Анализирую контекст и готовлю ответ"
        : activeRuntime.session.status === "listening"
          ? "Слушаю и фиксирую задачу"
          : "Готов к диалогу";

  return (
    <motion.div
      initial={{ opacity: 0, y: 18, scale: 0.995 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
      className={`w-full ${className} overflow-hidden rounded-[2rem] bg-[radial-gradient(circle_at_28%_18%,rgba(255,255,255,0.06),rgba(16,16,22,0.94)_38%,rgba(10,10,14,0.98)_100%)] shadow-[0_40px_120px_rgba(0,0,0,0.55)]`}
    >
      <motion.section
        className="agent-scene relative min-h-[74rem] w-full overflow-hidden md:min-h-[88rem]"
        initial={{ opacity: 0.2 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.35, ease: "easeOut" }}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1.3, ease: "easeOut" }}
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_22%_46%,rgba(231,197,154,0.24),rgba(10,10,12,0)_48%),radial-gradient(circle_at_72%_28%,rgba(255,255,255,0.08),rgba(10,10,12,0)_43%)]"
        />
        <motion.div
          animate={{
            opacity: orbAuraOpacity,
            scale: orbState === "speaking" ? 1.06 : orbState === "thinking" ? 1.045 : 1,
          }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          className="pointer-events-none absolute -left-[16%] top-[4%] h-[68%] w-[62%] rounded-full bg-[radial-gradient(circle_at_58%_52%,rgba(231,197,154,0.46),rgba(231,197,154,0.16)_36%,rgba(8,8,12,0)_72%)] blur-2xl"
        />
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1.6, delay: 0.5, ease: "easeOut" }}
          className="pointer-events-none absolute inset-x-[-6%] bottom-[10%] h-[58%] overflow-hidden"
        >
          <Threads
            color={AGENT_THREADS_RGB}
            amplitude={threadsPreset.amplitude}
            distance={threadsPreset.distance}
            flow={effectiveFlow}
            pulse={effectivePulse}
            complexity={threadsPreset.complexity}
            orbOrigin={[0.42, 0.39]}
            orbInfluence={threadsPreset.orbInfluence}
            orbWarp={threadsPreset.orbWarp}
            orbRadius={threadsPreset.orbRadius}
            className="h-full w-full opacity-100 [mask-image:linear-gradient(to_top,rgba(0,0,0,1),rgba(0,0,0,0.5),transparent)]"
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 140, damping: 26, mass: 0.9, delay: 0.35 }}
          className="relative z-10 grid min-h-[66rem] grid-cols-1 gap-6 p-5 sm:p-6 md:min-h-[82rem] md:grid-cols-5 md:items-start md:gap-8 md:px-8 md:pb-20 md:pt-7"
        >
          <motion.div
            layout
            className={`min-w-0 md:col-span-2 ${
              dockOrb
                ? "min-h-[24rem] md:min-h-[38rem]"
                : "min-h-[26rem] md:col-span-5 md:min-h-[39rem]"
            }`}
            transition={{ duration: 0.58, ease: [0.22, 1, 0.36, 1] }}
          >
            <motion.div
              animate={
                dockOrb
                  ? { x: 0, y: 0, justifyContent: "flex-start", alignItems: "flex-end" }
                  : { x: 0, y: 0, justifyContent: "center", alignItems: "center" }
              }
              transition={{ duration: 0.58, ease: [0.22, 1, 0.36, 1] }}
              onHoverStart={() => setIsHover(true)}
              onHoverEnd={() => setIsHover(false)}
              className={`flex h-full ${
                dockOrb
                  ? "items-center justify-center md:items-end md:justify-start md:pb-8 md:pl-6"
                  : "items-center justify-center md:justify-center md:pb-0 md:pl-0"
              }`}
            >
              <motion.div
                initial={{ opacity: 0, y: 12, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 1.05, delay: 0.55, ease: [0.22, 1, 0.36, 1] }}
                className="flex flex-col items-center gap-4 md:items-start"
              >
                <AgentOrb
                  state={orbState}
                  open={dockOrb}
                  onToggle={handleOrbToggle}
                />
                <div className="text-center md:pl-3 md:text-left">
                  <p className="mono text-xs uppercase tracking-[0.24em] text-[var(--color-ash-gray)]">
                    Я здесь, чтобы помогать
                  </p>
                  <p className="mt-1 text-sm text-[var(--color-ash-gray)]">{statusText}</p>
                </div>
              </motion.div>
            </motion.div>
          </motion.div>

          {chatOpen ? (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }}
              className="min-w-0 md:col-span-3 md:pt-5"
            >
              <ChatPanelTransition open={chatOpen} className="w-full">
                <AgentChatPanel
                  messages={activeRuntime.session.messages}
                  onSendMessage={activeRuntime.sendMessage}
                  modeLabel={runtime ? "dialog" : "demo"}
                  errorMessage={activeRuntime.session.errorMessage}
                />
              </ChatPanelTransition>
            </motion.div>
          ) : null}
        </motion.div>
      </motion.section>
    </motion.div>
  );
}
