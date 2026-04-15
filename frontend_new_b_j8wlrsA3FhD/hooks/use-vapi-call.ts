"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Vapi from "@vapi-ai/web";
import type { Turn, UiState, VapiMessage } from "@/types/voice";
import { isTranscriptMessage, isSpeechUpdateMessage, isToolCallsMessage } from "@/types/voice";
import { useTranscriptHistory } from "./use-transcript-history";

function classifyError(err: unknown): string {
  if (typeof err !== "object" || err === null) return "Ошибка соединения";
  const msg = ((err as { message?: string }).message ?? "").toLowerCase();
  if (msg.includes("permission") || msg.includes("notallowed")) return "Разрешите доступ к микрофону";
  if (msg.includes("notfound") || msg.includes("device")) return "Микрофон недоступен";
  if (msg.includes("https") || msg.includes("secure")) return "Требуется HTTPS";
  if (msg.includes("notsupported") || msg.includes("browser")) return "Браузер не поддерживается";
  return "Ошибка соединения";
}

interface UseVapiCallOptions {
  publicKey?: string;
  assistantId?: string;
  onShowVideo?: (videoId: string) => void;
  onHideVideo?: () => void;
}

export type TranscriptProbe = {
  seq: number;
  ts: string;
  source: "vapi-message" | "call-start" | "call-end" | "speech-update" | "tool-calls";
  eventType: string;
  role?: "user" | "assistant";
  transcriptType?: "partial" | "final";
  transcript?: string;
  status?: string;
  raw: unknown;
};

type ConversationLikeMessage = {
  role?: string;
  text?: string;
  content?: unknown;
  message?: unknown;
  id?: string | number;
};

function extractText(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item;
        if (!item || typeof item !== "object") return "";
        const row = item as Record<string, unknown>;
        if (typeof row.text === "string") return row.text;
        if (typeof row.content === "string") return row.content;
        if (typeof row.value === "string") return row.value;
        return "";
      })
      .filter(Boolean)
      .join(" ")
      .trim();
  }
  if (!value || typeof value !== "object") return "";
  const obj = value as Record<string, unknown>;
  if (typeof obj.text === "string") return obj.text.trim();
  if (typeof obj.content === "string") return obj.content.trim();
  if (typeof obj.message === "string") return obj.message.trim();
  return "";
}

function normalizeUtterance(text: string): string {
  return text
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/([(\[{])\s+/g, "$1")
    .trim();
}

function extractLooseTranscript(raw: unknown): { role: "user" | "assistant"; transcriptType: "partial" | "final"; transcript: string } | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (obj.type !== "transcript") return null;
  const role = obj.role === "assistant" ? "assistant" : obj.role === "user" ? "user" : null;
  if (!role) return null;
  const transcript = extractText(obj.transcript) || extractText(obj.text) || extractText(obj.content);
  if (!transcript) return null;
  const t = obj.transcriptType === "final" ? "final" : "partial";
  return { role, transcriptType: t, transcript };
}

function normalizeConversationTurns(raw: unknown): Turn[] {
  if (!raw || typeof raw !== "object") return [];
  const root = raw as Record<string, unknown>;
  const candidate =
    (Array.isArray(root.conversation) && root.conversation) ||
    (Array.isArray(root.messages) && root.messages) ||
    ((root.conversation && typeof root.conversation === "object" && Array.isArray((root.conversation as Record<string, unknown>).messages))
      ? ((root.conversation as Record<string, unknown>).messages as unknown[])
      : null);
  if (!candidate) return [];

  const now = Date.now();
  const result: Turn[] = [];
  for (let i = 0; i < candidate.length; i += 1) {
    const row = candidate[i] as ConversationLikeMessage;
    const role = row.role;
    if (role !== "user" && role !== "assistant") continue;
    const text = normalizeUtterance(extractText(row.text ?? row.content ?? row.message ?? row));
    if (!text) continue;
    result.push({
      id: typeof row.id === "string" || typeof row.id === "number" ? String(row.id) : `conv-${role}-${i}`,
      role,
      text,
      isFinal: true,
      startedAt: now + i,
      updatedAt: now + i,
    });
  }
  return result;
}

function extractToolCalls(raw: unknown): Array<{ name?: string; arguments?: Record<string, unknown> }> {
  if (!raw || typeof raw !== "object") return [];
  const obj = raw as Record<string, unknown>;

  if (Array.isArray(obj.toolCalls)) {
    return obj.toolCalls as Array<{ name?: string; arguments?: Record<string, unknown> }>;
  }

  if (Array.isArray(obj.tool_calls)) {
    return (obj.tool_calls as Array<Record<string, unknown>>).map((item) => ({
      name: (item.function as Record<string, unknown> | undefined)?.name as string | undefined,
      arguments:
        typeof (item.function as Record<string, unknown> | undefined)?.arguments === "string"
          ? (() => {
              try {
                return JSON.parse((item.function as Record<string, unknown>).arguments as string) as Record<string, unknown>;
              } catch {
                return {};
              }
            })()
          : ((item.function as Record<string, unknown> | undefined)?.arguments as Record<string, unknown> | undefined),
    }));
  }

  if (obj.type === "tool-calls" && Array.isArray(obj.toolCalls)) {
    return obj.toolCalls as Array<{ name?: string; arguments?: Record<string, unknown> }>;
  }

  return [];
}

export function useVapiCall(options: UseVapiCallOptions = {}) {
  const {
    publicKey = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY ?? "",
    assistantId = process.env.NEXT_PUBLIC_VAPI_ASSISTANT_ID ?? "",
    onShowVideo,
    onHideVideo,
  } = options;

  const [uiState, setUiState] = useState<UiState>({
    callStatus: "idle",
    activeSpeaker: null,
  });
  const [transcriptLogs, setTranscriptLogs] = useState<TranscriptProbe[]>([]);
  const [conversationTurns, setConversationTurns] = useState<Turn[]>([]);

  const {
    turns: userTranscriptTurns,
    draftByRole,
    handleTranscriptMessage,
    finalizeRole,
    scheduleFinalizeRole,
    finalizeAll,
    clear: clearTranscript,
  } = useTranscriptHistory();

  const vapiRef = useRef<Vapi | null>(null);
  const activeSpeakerRef = useRef<"user" | "assistant" | null>(null);
  const eventLogSeqRef = useRef(0);
  const prevConversationRef = useRef<Turn[]>([]);
  const lastConvUpdateAtRef = useRef(0);
  const liveUserDraftRef = useRef<Turn | null>(null);

  const appendEventLog = useCallback((entry: Omit<TranscriptProbe, "seq" | "ts">) => {
    eventLogSeqRef.current += 1;
    const probe: TranscriptProbe = {
      seq: eventLogSeqRef.current,
      ts: new Date().toISOString(),
      ...entry,
    };
    setTranscriptLogs((prev) => [...prev, probe].slice(-400));

    if (typeof window !== "undefined") {
      const win = window as Window & { __DZEN_VAPI_TRANSCRIPTS__?: TranscriptProbe[] };
      const current = win.__DZEN_VAPI_TRANSCRIPTS__ ?? [];
      win.__DZEN_VAPI_TRANSCRIPTS__ = [...current, probe].slice(-400);
    }

    console.log("[VAPI_EVENT]", probe);
  }, []);

  const handleCallStart = useCallback(() => {
    activeSpeakerRef.current = null;
    appendEventLog({ source: "call-start", eventType: "call-start", raw: { type: "call-start" } });
    setUiState((prev) => ({ ...prev, callStatus: "in-call" }));
  }, [appendEventLog]);

  const handleCallEnd = useCallback(() => {
    finalizeAll();
    activeSpeakerRef.current = null;
    appendEventLog({ source: "call-end", eventType: "call-end", raw: { type: "call-end" } });
    setUiState({ callStatus: "ended", activeSpeaker: null });
  }, [appendEventLog, finalizeAll]);

  const handleSpeechStart = useCallback((role: "user" | "assistant") => {
    const previousRole = activeSpeakerRef.current;
    if (previousRole === "user" && role !== "user") {
      finalizeRole("user");
    }
    activeSpeakerRef.current = role;
    setUiState((prev) => ({ ...prev, activeSpeaker: role }));
  }, [finalizeRole]);

  const handleSpeechEnd = useCallback((role: "user" | "assistant") => {
    if (role === "user") scheduleFinalizeRole(role);
    if (activeSpeakerRef.current === role) activeSpeakerRef.current = null;
    setUiState((prev) => (prev.activeSpeaker === role ? { ...prev, activeSpeaker: null } : prev));
  }, [scheduleFinalizeRole]);

  const handleMessage = useCallback(
    (rawMsg: unknown) => {
      if (typeof rawMsg !== "object" || rawMsg === null) return;
      const msg = rawMsg as VapiMessage;

      // ── conversation-update: canonical source for both user & assistant ──
      if ((msg as { type?: string }).type === "conversation-update") {
        appendEventLog({
          source: "vapi-message",
          eventType: "conversation-update",
          raw: rawMsg,
        });
        const convTurns = normalizeConversationTurns(rawMsg);
        if (convTurns.length > 0) {
          const prev = prevConversationRef.current;
          const stable = convTurns.map((turn, i) => {
            const old = prev[i];
            if (old && old.role === turn.role && old.text === turn.text) return old;
            return turn;
          });
          prevConversationRef.current = stable;
          lastConvUpdateAtRef.current = Date.now();
          setConversationTurns(stable);
        }
        return;
      }

      // ── transcript: user → live draft; assistant → debug log only ────────
      if (isTranscriptMessage(msg)) {
        appendEventLog({
          source: "vapi-message",
          eventType: "transcript",
          role: msg.role,
          transcriptType: msg.transcriptType,
          transcript: msg.transcript,
          raw: msg,
        });
        if (msg.role === "user") {
          handleTranscriptMessage(msg);
          scheduleFinalizeRole("user", 1200);
        }
        return;
      }

      // ── loose transcript (non-standard shape): user only ─────────────────
      const looseTranscript = extractLooseTranscript(rawMsg);
      if (looseTranscript) {
        appendEventLog({
          source: "vapi-message",
          eventType: "transcript",
          role: looseTranscript.role,
          transcriptType: looseTranscript.transcriptType,
          transcript: looseTranscript.transcript,
          raw: rawMsg,
        });
        if (looseTranscript.role === "user") {
          handleTranscriptMessage({
            type: "transcript",
            role: "user",
            transcriptType: looseTranscript.transcriptType,
            transcript: looseTranscript.transcript,
          });
          scheduleFinalizeRole("user", 1200);
        }
        return;
      }

      // ── speech-update ────────────────────────────────────────────────────
      if (isSpeechUpdateMessage(msg)) {
        appendEventLog({
          source: "speech-update",
          eventType: msg.type,
          role: msg.role,
          status: msg.status,
          raw: msg,
        });
        if (msg.status === "started") handleSpeechStart(msg.role);
        else handleSpeechEnd(msg.role);
        return;
      }

      // ── tool-calls ───────────────────────────────────────────────────────
      if (isToolCallsMessage(msg)) {
        appendEventLog({
          source: "tool-calls",
          eventType: msg.type,
          raw: msg,
        });
        for (const toolCall of msg.toolCalls) {
          if (toolCall.name === "show_video") {
            const videoId = (toolCall.arguments?.videoId as string | undefined) ?? "";
            if (videoId) onShowVideo?.(videoId);
          } else if (toolCall.name === "hide_video") {
            onHideVideo?.();
          }
        }
        return;
      }

      const extracted = extractToolCalls(rawMsg);
      for (const toolCall of extracted) {
        if (toolCall.name === "show_video") {
          const videoId = (toolCall.arguments?.videoId as string | undefined) ?? "";
          if (videoId) onShowVideo?.(videoId);
        } else if (toolCall.name === "hide_video") {
          onHideVideo?.();
        }
      }

      appendEventLog({
        source: "vapi-message",
        eventType: (msg as { type?: string }).type ?? "unknown",
        raw: rawMsg,
      });
    },
    [
      appendEventLog,
      handleSpeechEnd,
      handleSpeechStart,
      handleTranscriptMessage,
      onHideVideo,
      onShowVideo,
      scheduleFinalizeRole,
    ]
  );

  const stopCall = useCallback(() => {
    try {
      finalizeAll();
      activeSpeakerRef.current = null;
      vapiRef.current?.stop();
    } finally {
      setUiState({ callStatus: "ended", activeSpeaker: null });
    }
  }, [finalizeAll]);

  const startCall = useCallback(async () => {
    if (!publicKey || !assistantId) {
      setUiState({
        callStatus: "error",
        activeSpeaker: null,
        errorMessage: "Не заданы NEXT_PUBLIC_VAPI_PUBLIC_KEY и NEXT_PUBLIC_VAPI_ASSISTANT_ID",
      });
      return;
    }

    try {
      clearTranscript();
      setConversationTurns([]);
      prevConversationRef.current = [];
      lastConvUpdateAtRef.current = 0;
      liveUserDraftRef.current = null;
      setTranscriptLogs([]);
      eventLogSeqRef.current = 0;
      setUiState({ callStatus: "connecting", activeSpeaker: null });

      if (vapiRef.current) {
        vapiRef.current.stop();
        vapiRef.current = null;
      }

      const vapi = new Vapi(publicKey);
      vapiRef.current = vapi;

      vapi.on("call-start", handleCallStart);
      vapi.on("call-end", handleCallEnd);
      vapi.on("message", handleMessage);

      await vapi.start(assistantId);
    } catch (err: unknown) {
      const errorMessage = classifyError(err);
      setUiState({ callStatus: "error", activeSpeaker: null, errorMessage });
      if (process.env.NODE_ENV === "development") console.error("[vapi] startCall error:", err);
    }
  }, [assistantId, clearTranscript, handleCallEnd, handleCallStart, handleMessage, publicKey]);

  const toggleCall = useCallback(() => {
    if (uiState.callStatus === "idle" || uiState.callStatus === "ended" || uiState.callStatus === "error") {
      void startCall();
    } else if (uiState.callStatus === "in-call") {
      stopCall();
    }
  }, [uiState.callStatus, startCall, stopCall]);

  useEffect(() => {
    return () => {
      try {
        vapiRef.current?.stop();
      } catch {
        // noop
      }
      vapiRef.current = null;
    };
  }, []);

  const clearTranscriptLogs = useCallback(() => setTranscriptLogs([]), []);

  // ── Build final turns array ─────────────────────────────────────────────
  //
  // Sources (strict separation):
  //   Assistant text  → ONLY from conversation-update (canonical model output)
  //   User text       → conversation-update for finalized, transcript for live draft
  //
  // Layers:
  //   1. conversationTurns    — canonical history (user + assistant)
  //   2. pending user turns   — committed transcript turns not yet in conversation-update
  //   3. live user draft      — partial speech currently in progress
  //
  const turns = useMemo(() => {
    const hasCanonical = conversationTurns.length > 0;
    const base: Turn[] = hasCanonical ? [...conversationTurns] : [];

    if (!hasCanonical) {
      // No conversation-update yet: show committed user turns from transcript
      base.push(...userTranscriptTurns);
    } else {
      // Append user turns committed after the latest conversation-update
      const cutoff = lastConvUpdateAtRef.current;
      for (const ut of userTranscriptTurns) {
        if (ut.startedAt > cutoff) {
          const alreadyPresent = base.some(
            (t) => t.role === "user" && t.text === ut.text
          );
          if (!alreadyPresent) base.push(ut);
        }
      }
    }

    // Append live user draft while user is speaking
    const userDraft = draftByRole.user?.trim();
    if (userDraft) {
      const lastUserText = [...base].reverse().find((t) => t.role === "user")?.text;
      if (lastUserText !== userDraft) {
        const prev = liveUserDraftRef.current;
        if (prev && prev.text === userDraft) {
          base.push(prev);
        } else {
          const now = Date.now();
          const draft: Turn = {
            id: "live-user-draft",
            role: "user",
            text: userDraft,
            isFinal: false,
            startedAt: prev?.startedAt ?? now,
            updatedAt: now,
          };
          liveUserDraftRef.current = draft;
          base.push(draft);
        }
      } else {
        liveUserDraftRef.current = null;
      }
    } else {
      liveUserDraftRef.current = null;
    }

    return base;
  }, [conversationTurns, draftByRole, userTranscriptTurns]);

  return {
    uiState,
    turns,
    transcriptLogs,
    showDebugLogs: true,
    clearTranscriptLogs,
    toggleCall,
    startCall,
    stopCall,
  };
}
