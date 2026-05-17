"use client";

import Vapi from "@vapi-ai/web";
import { enqueueRawDebugRecord } from "@/shared/debug-ingest-client";
import { buildVideoToolMessage } from "@/shared/video-tool-message";
import { useVoiceStore } from "@/shared/voice-store";
import { extractFinalTranscriptMessage, extractToolCalls, isSpeechUpdateMessage } from "@/shared/vapi-guards";
import { warmUpMicrophonePermission } from "@/audio/microphone";

function classifyStartError(err: unknown): string {
  if (typeof err !== "object" || err === null) return "Ошибка соединения";
  const msg = ((err as { message?: string }).message ?? "").toLowerCase();
  if (msg.includes("permission") || msg.includes("notallowed")) return "Разрешите доступ к микрофону";
  if (msg.includes("notfound") || msg.includes("device")) return "Микрофон недоступен";
  return "Не удалось начать звонок";
}

type VideoToolInvocation = {
  callId: string;
  name: "show_video" | "show_demo_video";
  videoKey: string;
  title?: string;
  reason?: string;
  startSeconds?: number;
};

function normalizeVideoKey(value: string): string {
  const key = value.trim().toLowerCase();
  if (key === "inspectra") return "agent_1";
  if (key === "anna") return "agent_2";
  if (key === "polevoy" || key === "ivan_polevoy" || key === "ivan-polevoy") return "agent_3";
  if (key === "metallica") return "agent_4";
  return key;
}

function resolveVideoSource(videoKey: string): { normalizedKey: string; src: string; title: string } | null {
  const normalizedKey = normalizeVideoKey(videoKey);
  const map: Record<string, { src: string; title: string }> = {
    agent_1: { src: "/media/videos/Agent1.mp4", title: "Inspectra Demo" },
    agent_2: { src: "/media/videos/Agent2.mp4", title: "Anna Demo" },
    agent_3: { src: "/media/videos/Agent3.mp4", title: "Ivan Polevoy Demo" },
    agent_4: { src: "/media/videos/Agent4.mp4", title: "Metallica Demo" },
  };
  const item = map[normalizedKey];
  return item ? { normalizedKey, ...item } : null;
}

function parseFunctionArguments(raw: unknown): Record<string, unknown> {
  if (!raw) return {};
  if (typeof raw === "object") return raw as Record<string, unknown>;
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as unknown;
      return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return {};
}

function extractVideoToolInvocations(raw: unknown): VideoToolInvocation[] {
  if (!raw || typeof raw !== "object") return [];
  const message = raw as Record<string, unknown>;
  const result: VideoToolInvocation[] = [];

  const toolBatches: unknown[][] = [];
  if (Array.isArray(message.toolCalls)) toolBatches.push(message.toolCalls);
  if (Array.isArray(message.toolCallList)) toolBatches.push(message.toolCallList);

  if (message.type === "conversation-update" && message.conversation && typeof message.conversation === "object") {
    const conversation = message.conversation as { messages?: Array<{ tool_calls?: unknown }> };
    for (const item of conversation.messages ?? []) {
      if (item && typeof item === "object" && Array.isArray(item.tool_calls)) {
        toolBatches.push(item.tool_calls);
      }
    }
  }

  for (const toolCalls of toolBatches) {
    for (const toolCallRaw of toolCalls) {
      if (!toolCallRaw || typeof toolCallRaw !== "object") continue;
      const toolCall = toolCallRaw as Record<string, unknown>;
      const fn =
        toolCall.function && typeof toolCall.function === "object"
          ? (toolCall.function as Record<string, unknown>)
          : null;
      const name = typeof fn?.name === "string" ? fn.name : null;
      if (name !== "show_video" && name !== "show_demo_video") continue;
      const args = parseFunctionArguments(fn?.arguments);
      const rawVideoKey = typeof args.videoKey === "string" ? args.videoKey : typeof args.video === "string" ? args.video : "";
      if (!rawVideoKey) continue;
      result.push({
        callId: typeof toolCall.id === "string" ? toolCall.id : crypto.randomUUID(),
        name,
        videoKey: rawVideoKey,
        title: typeof args.title === "string" ? args.title : undefined,
        reason: typeof args.reason === "string" ? args.reason : undefined,
        startSeconds: typeof args.startSeconds === "number" ? args.startSeconds : undefined,
      });
    }
  }

  return result;
}

/**
 * Imperative voice layer: no React in this module beyond reading/writing the zustand store.
 * UI components should call `getVoiceController()` only from the client.
 */
export class VoiceController {
  private vapi: Vapi | null = null;
  private currentSessionId: string | null = null;
  private currentCallId: string | null = null;
  private readonly debugLogMode: "minimal" | "verbose" = "minimal";
  private lastNetworkConnectionState: string | null = null;
  private lastNetworkQualityState: string | null = null;
  private lastUnparsedMessageSignature: string | null = null;
  private handledVideoToolCallIds = new Set<string>();

  private logEvent(type: string, payload: unknown, force = false) {
    if (!force && this.debugLogMode !== "verbose") return;
    let serialized = "";
    try {
      serialized = typeof payload === "string" ? payload : JSON.stringify(payload);
    } catch {
      serialized = String(payload);
    }
    useVoiceStore.getState().addDebugEvent({ type, payload: serialized });
  }

  private readonly onCallStart = () => {
    useVoiceStore.getState().setStatus("connected");
    this.logEvent("call-start", { ok: true }, true);
    this.persistRaw("call-start", { ok: true });
  };

  private readonly onCallEnd = () => {
    this.logEvent("call-end", { ok: true }, true);
    this.persistRaw("call-end", { ok: true });
    this.detach();
    const store = useVoiceStore.getState();
    store.setStatus("idle");
    store.setSpeaking(null);
    store.setRemoteVideoTrack(null);
  };

  private readonly onVideoTrack = (track: MediaStreamTrack) => {
    useVoiceStore.getState().setRemoteVideoTrack(track);
    useVoiceStore.getState().addTranscriptMessage({
      role: "system",
      content: `[video-track] ${track.kind} (${track.label || "remote"})`,
    });
    this.logEvent("video-track", {
      kind: track.kind,
      id: track.id,
      label: track.label,
      enabled: track.enabled,
      readyState: track.readyState,
    }, true);
    this.persistRaw("video-track", {
      kind: track.kind,
      id: track.id,
      label: track.label,
      enabled: track.enabled,
      readyState: track.readyState,
    });
  };

  private readonly onMessage = (raw: unknown) => {
    this.persistRaw("message", raw);
    const toolCalls = extractToolCalls(raw);
    const videoToolInvocations = extractVideoToolInvocations(raw);
    const transcript = extractFinalTranscriptMessage(raw);

    if (toolCalls.length > 0) {
      this.logEvent(
        "tool-calls",
        toolCalls.map((toolCall) => ({
          name: toolCall.name,
          status: toolCall.status,
          summary: toolCall.summary,
        })),
        true,
      );
      for (const toolCall of toolCalls) {
        useVoiceStore.getState().addToolEvent(toolCall);
      }
    }

    for (const invocation of videoToolInvocations) {
      if (this.handledVideoToolCallIds.has(invocation.callId)) continue;
      this.handledVideoToolCallIds.add(invocation.callId);
      const resolved = resolveVideoSource(invocation.videoKey);
      if (!resolved) {
        this.logEvent(
          "video-tool-unknown-key",
          { tool: invocation.name, callId: invocation.callId, videoKey: invocation.videoKey },
          true,
        );
        continue;
      }
      useVoiceStore.getState().addTranscriptMessage({
        role: "system",
        content: buildVideoToolMessage({
          videoKey: resolved.normalizedKey,
          src: resolved.src,
          title: invocation.title ?? resolved.title,
          reason: invocation.reason,
          startSeconds: invocation.startSeconds,
        }),
      });
      useVoiceStore.getState().addToolEvent({
        name: invocation.name,
        status: "done",
        summary: `video opened: ${resolved.normalizedKey}`,
        rawPayload: JSON.stringify(invocation),
      });

      // Best-effort client ack for tool-call contexts where assistant expects completion feedback.
      if (this.vapi) {
        try {
          this.vapi.send({
            type: "add-message",
            message: {
              role: "tool",
              tool_call_id: invocation.callId,
              content: `Success: opened ${resolved.normalizedKey}`,
            },
            triggerResponseEnabled: false,
          });
          this.logEvent(
            "video-tool-ack-sent",
            { callId: invocation.callId, tool: invocation.name, videoKey: resolved.normalizedKey },
            true,
          );
        } catch (error) {
          this.logEvent(
            "video-tool-ack-failed",
            { callId: invocation.callId, error: String(error) },
            true,
          );
        }
      }
    }

    if (transcript) {
      this.logEvent("transcript-final", transcript, true);
    } else if (this.debugLogMode === "verbose") {
      this.logEvent("message", raw);
    }

    if (!toolCalls.length && !transcript && !isSpeechUpdateMessage(raw) && raw && typeof raw === "object") {
      const record = raw as Record<string, unknown>;
      const summary = {
        type: typeof record.type === "string" ? record.type : "unknown",
        keys: Object.keys(record).slice(0, 25),
      };
      const signature = JSON.stringify(summary);
      if (signature !== this.lastUnparsedMessageSignature) {
        this.lastUnparsedMessageSignature = signature;
        this.logEvent("message-unparsed", summary, true);
      }
    }

    if (isSpeechUpdateMessage(raw)) {
      if (raw.status === "started") {
        useVoiceStore.getState().setSpeaking(raw.role);
      } else {
        useVoiceStore.getState().setSpeaking(null);
      }
    }
    if (transcript) {
      useVoiceStore.getState().addTranscriptMessage(transcript);
    }
  };

  private readonly onError = (error: unknown) => {
    this.logEvent("error", error, true);
    this.persistRaw("error", error);
  };

  private readonly onVolume = (volume: number) => {
    if (this.debugLogMode === "verbose") {
      this.logEvent("volume-level", { volume });
    }
  };

  private readonly onSpeechStart = () => {
    if (this.debugLogMode === "verbose") {
      this.logEvent("speech-start", { ok: true });
    }
  };

  private readonly onSpeechEnd = () => {
    if (this.debugLogMode === "verbose") {
      this.logEvent("speech-end", { ok: true });
    }
  };

  private readonly onNetworkQuality = (event: unknown) => {
    if (this.debugLogMode !== "verbose") {
      if (!event || typeof event !== "object") return;
      const e = event as Record<string, unknown>;
      const level = typeof e.level === "string" ? e.level : typeof e.quality === "string" ? e.quality : null;
      if (!level) return;
      if (level === this.lastNetworkQualityState) return;
      this.lastNetworkQualityState = level;
      this.logEvent("network-quality-change", { level }, true);
      this.persistRaw("network-quality-change", { level });
      return;
    }
    this.logEvent("network-quality-change", event);
    this.persistRaw("network-quality-change", event);
  };

  private readonly onNetworkConnection = (event: unknown) => {
    if (this.debugLogMode !== "verbose") {
      if (!event || typeof event !== "object") return;
      const e = event as Record<string, unknown>;
      const state =
        (typeof e.state === "string" && e.state) ||
        (typeof e.status === "string" && e.status) ||
        "unknown";
      if (state === this.lastNetworkConnectionState) return;
      this.lastNetworkConnectionState = state;
      this.logEvent("network-connection", { state }, true);
      this.persistRaw("network-connection", { state });
      return;
    }
    this.logEvent("network-connection", event);
    this.persistRaw("network-connection", event);
  };

  private readonly onDailyParticipantUpdated = (participant: unknown) => {
    if (this.debugLogMode === "verbose") {
      this.logEvent("daily-participant-updated", participant);
      this.persistRaw("daily-participant-updated", participant);
    }
  };

  private readonly onCallStartSuccess = (event: unknown) => {
    if (event && typeof event === "object") {
      const callId = (event as { callId?: unknown }).callId;
      if (typeof callId === "string") {
        this.currentCallId = callId;
      }
    }
    this.logEvent("call-start-success", event, true);
    this.persistRaw("call-start-success", event);
  };

  private readonly onCallStartFailed = (event: unknown) => {
    this.logEvent("call-start-failed", event, true);
    this.persistRaw("call-start-failed", event);
  };

  private persistRaw(eventType: string, payload: unknown) {
    if (!this.currentSessionId) return;
    enqueueRawDebugRecord({
      kind: "raw-event",
      sessionId: this.currentSessionId,
      callId: this.currentCallId,
      timestamp: new Date().toISOString(),
      eventType,
      payload,
    });
  }

  private detach() {
    if (!this.vapi) return;
    try {
      this.vapi.removeAllListeners();
    } catch {
      /* noop */
    }
    this.vapi = null;
  }

  async start(publicKey: string, assistantId: string) {
    const store = useVoiceStore.getState();
    store.reset();
    store.clearDebugEvents();
    store.clearToolEvents();
    this.currentSessionId = crypto.randomUUID();
    this.currentCallId = null;
    this.lastNetworkConnectionState = null;
    this.lastNetworkQualityState = null;
    this.lastUnparsedMessageSignature = null;
    this.handledVideoToolCallIds.clear();

    if (!publicKey.trim() || !assistantId.trim()) {
      store.setError("Задайте NEXT_PUBLIC_VAPI_PUBLIC_KEY и NEXT_PUBLIC_VAPI_ASSISTANT_ID в .env.local");
      return;
    }

    store.setStatus("connecting");

    const mic = await warmUpMicrophonePermission();
    if (!mic.ok) {
      useVoiceStore.getState().setError(mic.reason);
      return;
    }

    try {
      if (this.vapi) {
        try {
          this.vapi.stop();
        } catch {
          /* noop */
        }
        this.detach();
      }

      const vapi = new Vapi(publicKey);
      this.vapi = vapi;
      vapi.on("call-start", this.onCallStart);
      vapi.on("call-end", this.onCallEnd);
      vapi.on("message", this.onMessage);
      vapi.on("video", this.onVideoTrack);
      vapi.on("error", this.onError);
      vapi.on("volume-level", this.onVolume);
      vapi.on("speech-start", this.onSpeechStart);
      vapi.on("speech-end", this.onSpeechEnd);
      vapi.on("network-quality-change", this.onNetworkQuality);
      vapi.on("network-connection", this.onNetworkConnection);
      vapi.on("daily-participant-updated", this.onDailyParticipantUpdated);
      vapi.on("call-start-success", this.onCallStartSuccess);
      vapi.on("call-start-failed", this.onCallStartFailed);

      await vapi.start(assistantId);
    } catch (err) {
      console.error("[agent-next vapi]", err);
      this.detach();
      useVoiceStore.getState().setError(classifyStartError(err));
    }
  }

  stop() {
    try {
      this.vapi?.stop();
    } catch {
      /* noop */
    } finally {
      this.detach();
      const store = useVoiceStore.getState();
      store.setStatus("idle");
      store.setSpeaking(null);
      store.setRemoteVideoTrack(null);
    }
  }

  sendText(message: string): boolean {
    const text = message.trim();
    if (!text || !this.vapi) return false;
    try {
      this.vapi.send({
        type: "add-message",
        message: {
          role: "user",
          content: text,
        },
        triggerResponseEnabled: true,
      });
      this.logEvent("text-message-sent", { role: "user", content: text }, true);
      const store = useVoiceStore.getState();
      if (store.status !== "speaking" && store.status !== "error") {
        store.setStatus("connected");
      }
      return true;
    } catch (err) {
      console.error("[agent-next vapi send]", err);
      useVoiceStore.getState().setError("Не удалось отправить сообщение агенту");
      return false;
    }
  }

  dispose() {
    this.stop();
  }
}

let singleton: VoiceController | null = null;

export function getVoiceController(): VoiceController {
  if (!singleton) singleton = new VoiceController();
  return singleton;
}
