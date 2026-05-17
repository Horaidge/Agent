import { create } from "zustand";

/** High-level UI / session phases for voice foundation. */
export type VoiceStatus = "idle" | "connecting" | "connected" | "speaking" | "error";

export type VoiceTranscriptMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
};

export type VoiceDebugEvent = {
  id: string;
  timestamp: string;
  type: string;
  payload: string;
};

export type VoiceToolEvent = {
  id: string;
  name: string;
  status: "queued" | "running" | "done";
  summary: string;
  rawPayload?: string;
  timestamp: string;
};

export type VoiceSlice = {
  status: VoiceStatus;
  errorMessage: string | null;
  /** Who is currently speaking when status is `speaking`. */
  activeSpeaker: "user" | "assistant" | null;
  remoteVideoTrack: MediaStreamTrack | null;
  transcriptMessages: VoiceTranscriptMessage[];
  toolEvents: VoiceToolEvent[];
  debugEvents: VoiceDebugEvent[];
  setStatus: (status: VoiceStatus) => void;
  setError: (message: string | null) => void;
  setSpeaking: (role: "user" | "assistant" | null) => void;
  setRemoteVideoTrack: (track: MediaStreamTrack | null) => void;
  addTranscriptMessage: (message: Omit<VoiceTranscriptMessage, "id" | "timestamp">) => void;
  addToolEvent: (event: Omit<VoiceToolEvent, "id" | "timestamp">) => void;
  clearToolEvents: () => void;
  clearTranscriptMessages: () => void;
  addDebugEvent: (event: Omit<VoiceDebugEvent, "id" | "timestamp">) => void;
  clearDebugEvents: () => void;
  hydrateDebugSnapshot: (snapshot: {
    transcriptMessages?: VoiceTranscriptMessage[];
    toolEvents?: VoiceToolEvent[];
    debugEvents?: VoiceDebugEvent[];
  }) => void;
  /** After call ends or error cleared. */
  reset: () => void;
};

const initial = {
  status: "idle" as VoiceStatus,
  errorMessage: null as string | null,
  activeSpeaker: null as "user" | "assistant" | null,
  remoteVideoTrack: null as MediaStreamTrack | null,
  transcriptMessages: [] as VoiceTranscriptMessage[],
  toolEvents: [] as VoiceToolEvent[],
  debugEvents: [] as VoiceDebugEvent[],
};

export const useVoiceStore = create<VoiceSlice>((set) => ({
  ...initial,
  setStatus: (status) =>
    set((s) => ({
      status,
      errorMessage: status === "error" ? s.errorMessage : null,
    })),
  setError: (errorMessage) =>
    set({
      status: "error",
      errorMessage,
      activeSpeaker: null,
    }),
  setSpeaking: (activeSpeaker) =>
    set((s) => {
      if (s.status !== "connected" && s.status !== "speaking") return s;
      if (activeSpeaker) {
        return { status: "speaking", activeSpeaker };
      }
      return { status: "connected", activeSpeaker: null };
    }),
  setRemoteVideoTrack: (remoteVideoTrack) => set({ remoteVideoTrack }),
  addTranscriptMessage: (message) =>
    set((s) => {
      const content = message.content.trim();
      if (!content) return s;
      const previous = s.transcriptMessages.at(-1);
      if (previous && previous.role === message.role && previous.content === content) {
        return s;
      }
      return {
        transcriptMessages: [
          ...s.transcriptMessages,
          {
            id: crypto.randomUUID(),
            role: message.role,
            content,
            timestamp: new Date().toISOString(),
          },
        ],
      };
    }),
  addToolEvent: (event) =>
    set((s) => {
      const previous = s.toolEvents.at(-1);
      if (
        previous &&
        previous.name === event.name &&
        previous.status === event.status &&
        previous.summary === event.summary
      ) {
        return s;
      }
      return {
        toolEvents: [
          ...s.toolEvents.slice(-99),
          {
            id: crypto.randomUUID(),
            name: event.name,
            status: event.status,
            summary: event.summary,
            rawPayload: event.rawPayload,
            timestamp: new Date().toISOString(),
          },
        ],
      };
    }),
  clearToolEvents: () => set({ toolEvents: [] }),
  clearTranscriptMessages: () => set({ transcriptMessages: [] }),
  addDebugEvent: (event) =>
    set((s) => ({
      debugEvents: [
        ...s.debugEvents.slice(-199),
        {
          id: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          type: event.type,
          payload: event.payload,
        },
      ],
    })),
  clearDebugEvents: () => set({ debugEvents: [] }),
  hydrateDebugSnapshot: (snapshot) =>
    set({
      transcriptMessages: snapshot.transcriptMessages ?? [],
      toolEvents: snapshot.toolEvents ?? [],
      debugEvents: snapshot.debugEvents ?? [],
    }),
  reset: () => set(initial),
}));
