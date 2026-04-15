"use client";

import { memo, useEffect, useRef } from "react";
import type { Turn } from "@/types/voice";

interface VoiceTranscriptHistoryProps {
  turns: Turn[];
  isVisible: boolean;
}

export function VoiceTranscriptHistory({ turns, isVisible }: VoiceTranscriptHistoryProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const prevTurnsLengthRef = useRef(0);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;

    const distanceFromBottom = el.scrollHeight - (el.scrollTop + el.clientHeight);
    shouldAutoScrollRef.current = distanceFromBottom < 56;
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const isNewTurn = turns.length > prevTurnsLengthRef.current;
    prevTurnsLengthRef.current = turns.length;

    // Do not force-scroll if user intentionally moved up.
    if (!shouldAutoScrollRef.current) return;

    // Smooth only when a finalized turn is appended.
    el.scrollTo({
      top: el.scrollHeight,
      behavior: isNewTurn ? "smooth" : "auto",
    });
  }, [turns]);

  if (!isVisible || turns.length === 0) return null;

  return (
    <div className="w-full max-w-[560px] mx-auto px-4">
      <div
        className="rounded-[18px] border border-white/8 bg-[#10121A]/88 backdrop-blur-sm px-3 py-3"
        style={{ minHeight: "30vh", height: "36vh", maxHeight: "40vh" }}
      >
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="chat-scroll-area h-full overflow-y-auto pr-2"
          aria-label="История разговора"
          role="log"
          aria-live="polite"
        >
          <div className="flex flex-col gap-2.5">
            {turns.map((turn) => (
              // Stable key from persistent turn.id (never based on text/chunk/time).
              <MemoTurnRow key={turn.id} turn={turn} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function TurnRow({ turn }: { turn: Turn }) {
  const isUser = turn.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[78%] px-3.5 py-2.5 rounded-2xl ${isUser ? "rounded-br-md" : "rounded-bl-md"}`}
        style={{
          background: isUser ? "rgba(124, 58, 237, 0.16)" : "rgba(34, 211, 238, 0.10)",
          border: isUser ? "1px solid rgba(124, 58, 237, 0.28)" : "1px solid rgba(34, 211, 238, 0.20)",
        }}
      >
        <p
          className="text-[9px] font-semibold tracking-widest mb-1 leading-none"
          style={{ color: isUser ? "rgba(167, 139, 250, 0.72)" : "rgba(34, 211, 238, 0.68)" }}
        >
          {isUser ? "YOU" : "AI"}
        </p>

        <p
          className="text-sm leading-relaxed break-words"
          style={{ color: turn.isFinal ? "rgba(232, 234, 240, 0.90)" : "rgba(232, 234, 240, 0.68)" }}
        >
          {turn.text}
          {!turn.isFinal && <span style={{ color: isUser ? "#A78BFA" : "#22D3EE" }}> ▋</span>}
        </p>
      </div>
    </div>
  );
}

// Memoized row keeps prior bubbles stable when new finalized turns arrive.
const MemoTurnRow = memo(TurnRow, (prev, next) => prev.turn === next.turn);
