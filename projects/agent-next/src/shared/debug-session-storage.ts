import type { VoiceDebugEvent, VoiceToolEvent, VoiceTranscriptMessage } from "@/shared/voice-store";

export type DebugSessionSnapshot = {
  updatedAt: string;
  status: string;
  errorMessage: string | null;
  transcriptMessages: VoiceTranscriptMessage[];
  toolEvents: VoiceToolEvent[];
  debugEvents: VoiceDebugEvent[];
};

const STORAGE_KEY = "agent-next.debug-session.v1";

export function loadDebugSessionSnapshot(): DebugSessionSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as DebugSessionSnapshot;
  } catch {
    return null;
  }
}

export function saveDebugSessionSnapshot(snapshot: DebugSessionSnapshot) {
  if (typeof window === "undefined") return;
  const hasUsefulData =
    snapshot.transcriptMessages.length > 0 ||
    snapshot.toolEvents.length > 0 ||
    snapshot.debugEvents.length > 0 ||
    !!snapshot.errorMessage;

  if (!hasUsefulData) return;

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Ignore quota/storage errors in dev mode.
  }
}

export function downloadDebugSessionSnapshot(snapshot: DebugSessionSnapshot) {
  if (typeof window === "undefined") return;
  const fileContent = JSON.stringify(snapshot, null, 2);
  const blob = new Blob([fileContent], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  a.href = url;
  a.download = `agent-debug-${stamp}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
