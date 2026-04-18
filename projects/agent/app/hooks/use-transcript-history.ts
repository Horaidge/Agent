"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Turn, VapiTranscriptMessage } from "@/types/voice";

function createTurnId(counter: number): string {
  return `turn-${counter}`;
}

const SILENCE_DEBOUNCE_MS = 650;

type Role = Turn["role"];
type DraftByRole = Partial<Record<Role, string>>;

type RoleBuffer = {
  committedText: string;
  partialText: string;
  startedAt: number;
  updatedAt: number;
};

function needsSpace(left: string, right: string): boolean {
  if (!left || !right) return false;
  const rightStartsWithPunct = /^[,.;:!?)]/.test(right);
  const leftEndsWithPunct = /[(\s]$|[([{]\s*$/.test(left);
  if (rightStartsWithPunct || leftEndsWithPunct) return false;
  return !left.endsWith(" ");
}

function mergeChunk(previousText: string, incomingText: string): string {
  const prev = previousText.trim();
  const next = incomingText.trim();

  if (!prev) return next;
  if (!next) return prev;
  if (next === prev) return prev;
  if (next.startsWith(prev)) return next;
  if (prev.startsWith(next) || prev.endsWith(next)) return prev;
  return `${prev}${needsSpace(prev, next) ? " " : ""}${next}`;
}

function normalizeUtterance(text: string): string {
  const normalized = text
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/([(\[{])\s+/g, "$1")
    .trim();

  // Collapse adjacent duplicate words: "вопросы вопрос" -> "вопросы"
  let result = normalized;
  let prev = "";
  const duplicateWordRegex = /(\p{L}[\p{L}\p{M}\p{N}'-]*)\s+\1\b/giu;
  while (result !== prev) {
    prev = result;
    result = result.replace(duplicateWordRegex, "$1");
  }

  return result;
}

export function useTranscriptHistory() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const turnsRef = useRef<Turn[]>([]);
  const turnIdCounterRef = useRef(0);
  const [draftByRole, setDraftByRole] = useState<DraftByRole>({});
  const roleBuffersRef = useRef<Partial<Record<Role, RoleBuffer>>>({});
  const silenceTimersRef = useRef<Partial<Record<Role, ReturnType<typeof setTimeout>>>>({});

  const updateTurns = useCallback((updater: (prev: Turn[]) => Turn[]) => {
    setTurns((prev) => {
      const next = updater(prev);
      turnsRef.current = next;
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    turnsRef.current = [];
    roleBuffersRef.current = {};
    setDraftByRole({});
    for (const role of Object.keys(silenceTimersRef.current) as Role[]) {
      const timer = silenceTimersRef.current[role];
      if (timer) clearTimeout(timer);
    }
    silenceTimersRef.current = {};
    setTurns([]);
  }, []);

  const createNewTurn = useCallback((role: Turn["role"], text: string, isFinal: boolean, now: number): Turn => {
    turnIdCounterRef.current += 1;
    return {
      id: createTurnId(turnIdCounterRef.current),
      role,
      text,
      isFinal,
      startedAt: now,
      updatedAt: now,
    };
  }, []);

  const commitRoleBuffer = useCallback(
    (role: Role) => {
      const buffer = roleBuffersRef.current[role];
      if (!buffer) return;

      const composed = mergeChunk(buffer.committedText, buffer.partialText);
      const normalized = normalizeUtterance(composed);
      delete roleBuffersRef.current[role];
      setDraftByRole((prev) => ({ ...prev, [role]: "" }));

      if (!normalized) return;

      updateTurns((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === role && last.isFinal && last.text === normalized) return prev;
        return [...prev, createNewTurn(role, normalized, true, Date.now())];
      });
    },
    [createNewTurn, updateTurns]
  );

  const finalizeRole = useCallback(
    (role: Role) => {
      const timer = silenceTimersRef.current[role];
      if (timer) clearTimeout(timer);
      delete silenceTimersRef.current[role];
      commitRoleBuffer(role);
    },
    [commitRoleBuffer]
  );

  const scheduleFinalizeRole = useCallback(
    (role: Role, delayMs: number = SILENCE_DEBOUNCE_MS) => {
      const timer = silenceTimersRef.current[role];
      if (timer) clearTimeout(timer);
      silenceTimersRef.current[role] = setTimeout(() => {
        commitRoleBuffer(role);
        delete silenceTimersRef.current[role];
      }, delayMs);
    },
    [commitRoleBuffer]
  );

  const finalizeAll = useCallback(() => {
    finalizeRole("user");
    finalizeRole("assistant");
  }, [finalizeRole]);

  const handleTranscriptMessage = useCallback(
    (msg: VapiTranscriptMessage) => {
      const { role, transcriptType } = msg;
      const transcript = (msg.transcript ?? "").trim();
      const now = Date.now();

      if (!transcript) return;

      const buffer = roleBuffersRef.current[role];
      if (!buffer) {
        roleBuffersRef.current[role] = {
          committedText: transcriptType === "final" ? transcript : "",
          partialText: transcriptType === "partial" ? transcript : "",
          startedAt: now,
          updatedAt: now,
        };
      } else {
        if (transcriptType === "partial") {
          roleBuffersRef.current[role] = { ...buffer, partialText: transcript, updatedAt: now };
        } else {
          // final in Vapi can be a segment; keep accumulating in committed text.
          const mergedFinal = mergeChunk(buffer.committedText, transcript);
          roleBuffersRef.current[role] = { ...buffer, committedText: mergedFinal, partialText: "", updatedAt: now };
        }
      }

      const latest = roleBuffersRef.current[role];
      const liveText = latest ? mergeChunk(latest.committedText, latest.partialText) : "";
      setDraftByRole((prev) => (prev[role] === liveText ? prev : { ...prev, [role]: liveText }));

      // Never commit from transcript chunks directly.
      // Vapi final chunks are often just segments of the same utterance.
      // Commit happens only from speech-update events in use-vapi-call.
    },
    []
  );

  useEffect(() => {
    return () => {
      for (const role of Object.keys(silenceTimersRef.current) as Role[]) {
        const timer = silenceTimersRef.current[role];
        if (timer) clearTimeout(timer);
      }
    };
  }, []);

  return { turns, draftByRole, handleTranscriptMessage, finalizeRole, scheduleFinalizeRole, finalizeAll, clear };
}
