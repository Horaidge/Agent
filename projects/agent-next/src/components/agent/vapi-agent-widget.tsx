"use client";

import { useEffect, useMemo, useRef } from "react";
import { AgentWidget } from "@/components/agent/agent-widget";
import type { AgentRuntimeAdapter, AgentSessionState } from "@/components/agent/types";
import { useVoiceSession } from "@/orchestration/use-voice-session";
import {
  loadDebugSessionSnapshot,
  saveDebugSessionSnapshot,
  type DebugSessionSnapshot,
} from "@/shared/debug-session-storage";
import { useVoiceStore } from "@/shared/voice-store";

type VapiAgentWidgetProps = {
  publicKey: string;
  assistantId: string;
  className?: string;
};

function mapVoiceStatusToAgent(
  status: "idle" | "connecting" | "connected" | "speaking" | "error",
): AgentSessionState["status"] {
  if (status === "error") return "error";
  if (status === "speaking") return "speaking";
  if (status === "connecting") return "listening";
  if (status === "connected") return "listening";
  return "idle";
}

function mapActiveSpeakerToTools(
  activeSpeaker: "user" | "assistant" | null,
): AgentSessionState["tools"] {
  if (!activeSpeaker) return [];
  return [
    {
      id: "live-speaker",
      name: "webrtc-stream",
      status: "running",
      summary: activeSpeaker === "assistant" ? "Ассистент говорит в live-потоке." : "Пользователь говорит.",
    },
  ];
}

export function VapiAgentWidget({ publicKey, assistantId, className }: VapiAgentWidgetProps) {
  const {
    status,
    errorMessage,
    activeSpeaker,
    remoteVideoTrack,
    transcriptMessages,
    toolEvents,
    debugEvents,
    start,
    stop,
    sendText,
  } = useVoiceSession(publicKey, assistantId);
  const envError =
    !publicKey.trim() || !assistantId.trim()
      ? "Нужно заполнить NEXT_PUBLIC_VAPI_PUBLIC_KEY и NEXT_PUBLIC_VAPI_ASSISTANT_ID в .env.local"
      : null;
  const hydrateDebugSnapshot = useVoiceStore((s) => s.hydrateDebugSnapshot);
  const didHydrateRef = useRef(false);

  useEffect(() => {
    if (didHydrateRef.current) return;
    didHydrateRef.current = true;
    const snapshot = loadDebugSessionSnapshot();
    if (!snapshot) return;
    hydrateDebugSnapshot({
      transcriptMessages: snapshot.transcriptMessages,
      toolEvents: snapshot.toolEvents,
      debugEvents: snapshot.debugEvents,
    });
  }, [hydrateDebugSnapshot]);

  useEffect(() => {
    const snapshot: DebugSessionSnapshot = {
      updatedAt: new Date().toISOString(),
      status,
      errorMessage: envError ?? errorMessage,
      transcriptMessages,
      toolEvents,
      debugEvents,
    };
    saveDebugSessionSnapshot(snapshot);
  }, [status, envError, errorMessage, transcriptMessages, toolEvents, debugEvents]);

  const runtime = useMemo<AgentRuntimeAdapter>(
    () => {
      const mergedTools: AgentSessionState["tools"] = [
        ...toolEvents,
        ...mapActiveSpeakerToTools(activeSpeaker),
      ];
      return {
        session: {
          status: mapVoiceStatusToAgent(status),
          activeSpeaker,
          errorMessage: envError ?? errorMessage ?? undefined,
          liveVideoTrack: remoteVideoTrack,
          messages: transcriptMessages,
          tools: mergedTools,
          debugEvents,
        },
        openSession: start,
        closeSession: stop,
        sendMessage: (text: string) => {
          if (!sendText(text)) {
            console.warn("[agent-next] text message skipped: no active call");
          }
        },
      };
    },
    [
      status,
      envError,
      errorMessage,
      activeSpeaker,
      remoteVideoTrack,
      transcriptMessages,
      toolEvents,
      debugEvents,
      start,
      stop,
      sendText,
    ],
  );

  return <AgentWidget className={className} runtime={runtime} />;
}
