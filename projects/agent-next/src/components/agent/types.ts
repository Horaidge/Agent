export type AgentOrbVisualState =
  | "idle"
  | "hover"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

export const AGENT_ORB_STATE_PRIORITY: AgentOrbVisualState[] = [
  "error",
  "speaking",
  "thinking",
  "listening",
  "hover",
  "idle",
];

export type AgentChatRole = "user" | "assistant" | "system";

export type AgentChatMessage = {
  id: string;
  role: AgentChatRole;
  content: string;
  timestamp: string;
};

export type AgentToolItem = {
  id: string;
  name: string;
  status: "queued" | "running" | "done";
  summary: string;
  rawPayload?: string;
};

export type AgentDebugEvent = {
  id: string;
  timestamp: string;
  type: string;
  payload: string;
};

export type AgentSessionState = {
  status: Exclude<AgentOrbVisualState, "hover">;
  activeSpeaker?: "user" | "assistant" | null;
  errorMessage?: string;
  liveVideoTrack?: MediaStreamTrack | null;
  messages: AgentChatMessage[];
  tools: AgentToolItem[];
  debugEvents?: AgentDebugEvent[];
};

export type AgentRuntimeAdapter = {
  session: AgentSessionState;
  openSession: () => void;
  closeSession: () => void;
  sendMessage: (text: string) => void;
  setStatus?: (status: AgentSessionState["status"]) => void;
};
