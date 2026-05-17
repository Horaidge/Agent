"use client";

import { useCallback, useEffect } from "react";
import { useVoiceStore } from "@/shared/voice-store";
import { getVoiceController } from "@/orchestration/voice-controller";

export function useVoiceSession(publicKey: string, assistantId: string) {
  const status = useVoiceStore((s) => s.status);
  const errorMessage = useVoiceStore((s) => s.errorMessage);
  const activeSpeaker = useVoiceStore((s) => s.activeSpeaker);
  const remoteVideoTrack = useVoiceStore((s) => s.remoteVideoTrack);
  const transcriptMessages = useVoiceStore((s) => s.transcriptMessages);
  const toolEvents = useVoiceStore((s) => s.toolEvents);
  const debugEvents = useVoiceStore((s) => s.debugEvents);

  const start = useCallback(() => {
    void getVoiceController().start(publicKey, assistantId);
  }, [publicKey, assistantId]);

  const stop = useCallback(() => {
    getVoiceController().stop();
  }, []);

  const toggle = useCallback(() => {
    if (status === "idle" || status === "error") {
      void getVoiceController().start(publicKey, assistantId);
      return;
    }
    if (status === "connecting") return;
    getVoiceController().stop();
  }, [status, publicKey, assistantId]);

  const sendText = useCallback((text: string) => {
    return getVoiceController().sendText(text);
  }, []);

  useEffect(() => {
    return () => {
      getVoiceController().dispose();
    };
  }, []);

  return {
    status,
    errorMessage,
    activeSpeaker,
    remoteVideoTrack,
    transcriptMessages,
    toolEvents,
    debugEvents,
    start,
    stop,
    toggle,
    sendText,
  };
}
