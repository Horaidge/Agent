// ─── Core domain types ──────────────────────────────────────────────────────

export type Turn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  isFinal: boolean;
  startedAt: number;
  updatedAt: number;
};

export type UiState = {
  callStatus: "idle" | "connecting" | "in-call" | "ended" | "error";
  activeSpeaker: "user" | "assistant" | null;
  callId?: string;
  errorMessage?: string;
};

export type VideoItem = {
  id: string;
  title: string;
  description: string;
  thumbnail: string;
  videoUrl: string;
  tags: string[];
  duration: string;
};

export type MediaState = {
  activeVideo: VideoItem | null;
  isVideoOpen: boolean;
};

// ─── Vapi event payload types ────────────────────────────────────────────────

export type VapiTranscriptMessage = {
  type: "transcript";
  role: "user" | "assistant";
  transcriptType: "partial" | "final";
  transcript: string;
};

export type VapiSpeechUpdateMessage = {
  type: "speech-update";
  role: "user" | "assistant";
  status: "started" | "stopped";
};

export type VapiToolCall = {
  name: string;
  arguments: Record<string, unknown>;
};

export type VapiToolCallsMessage = {
  type: "tool-calls";
  toolCalls: VapiToolCall[];
};

export type VapiMessage =
  | VapiTranscriptMessage
  | VapiSpeechUpdateMessage
  | VapiToolCallsMessage
  | { type: string; [key: string]: unknown };

// ─── Type guards ─────────────────────────────────────────────────────────────

export function isTranscriptMessage(msg: VapiMessage): msg is VapiTranscriptMessage {
  return (
    msg.type === "transcript" &&
    "role" in msg &&
    "transcriptType" in msg &&
    "transcript" in msg
  );
}

export function isSpeechUpdateMessage(msg: VapiMessage): msg is VapiSpeechUpdateMessage {
  return (
    msg.type === "speech-update" &&
    "role" in msg &&
    "status" in msg
  );
}

export function isToolCallsMessage(msg: VapiMessage): msg is VapiToolCallsMessage {
  return msg.type === "tool-calls" && Array.isArray((msg as VapiToolCallsMessage).toolCalls);
}
