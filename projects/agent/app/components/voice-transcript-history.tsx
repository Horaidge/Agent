"use client";

import { memo, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ChatMessage, ChatTextMessage } from "@/types/voice";
import { ChatVideoMessage } from "@/components/chat-video-message";

interface VoiceTranscriptHistoryProps {
  messages: ChatMessage[];
}

export function VoiceTranscriptHistory({ messages }: VoiceTranscriptHistoryProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const prevLenRef = useRef(0);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - (el.scrollTop + el.clientHeight);
    shouldAutoScrollRef.current = distanceFromBottom < 64;
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const appended = messages.length > prevLenRef.current;
    prevLenRef.current = messages.length;

    if (!shouldAutoScrollRef.current) return;

    el.scrollTo({
      top: el.scrollHeight,
      behavior: appended ? "smooth" : "auto",
    });
  }, [messages]);

  const empty = messages.length === 0;

  return (
    <div className="w-full max-w-[500px] px-1">
      <div
        className="chat-panel-glass flex flex-col overflow-hidden rounded-[22px] border shadow-[0_24px_64px_-28px_rgba(0,0,0,0.75)]"
        style={{
          minHeight: 280,
          height: "min(38vh, 360px)",
          maxHeight: 400,
          background: "rgba(12, 13, 18, 0.45)",
          borderColor: "rgba(255,255,255,0.08)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <div
          className="flex shrink-0 items-center justify-between border-b px-4 py-2.5"
          style={{ borderColor: "rgba(255,255,255,0.06)" }}
        >
          <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-[rgba(160,168,192,0.55)]">
            Диалог
          </span>
          <span className="text-[10px] text-[rgba(120,128,160,0.45)]">Dzen.AI</span>
        </div>

        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="chat-scroll-area flex-1 overflow-y-auto px-3 py-3"
          aria-label="История разговора"
          role="log"
          aria-live="polite"
        >
          {empty ? (
            <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 px-4 text-center">
              <p className="text-sm font-light text-[rgba(180,188,210,0.45)]">
                Нажмите на сферу, чтобы начать разговор с Максом.
              </p>
              <p className="text-xs text-[rgba(120,128,160,0.4)]">
                Текст ассистента — из ответа модели, не субтитры.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <AnimatePresence initial={false}>
                {messages.map((message) => (
                  message.type === "video" ? (
                    <ChatVideoMessage key={message.id} video={message.video} />
                  ) : (
                    <TurnBubbleRow key={message.id} turn={message} />
                  )
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const TurnBubbleRow = memo(
  function TurnBubbleRow({ turn }: { turn: ChatTextMessage }) {
    const isUser = turn.role === "user";

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
        className={`flex ${isUser ? "justify-end" : "justify-start"}`}
      >
        <div
          className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 ${isUser ? "rounded-br-md" : "rounded-bl-md"}`}
          style={{
            background: isUser
              ? "linear-gradient(135deg, rgba(100,65,180,0.22) 0%, rgba(70,50,130,0.14) 100%)"
              : "rgba(28, 32, 44, 0.65)",
            border: isUser ? "1px solid rgba(140,110,200,0.22)" : "1px solid rgba(90,140,180,0.15)",
            boxShadow: isUser
              ? "0 8px 28px -12px rgba(80,50,140,0.35)"
              : "0 8px 24px -14px rgba(20,40,60,0.4)",
          }}
        >
          <p
            className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em]"
            style={{ color: isUser ? "rgba(196,180,245,0.7)" : "rgba(130,200,220,0.65)" }}
          >
            {isUser ? "Вы" : "Макс · Dzen.AI"}
          </p>
          <p
            className="text-[13px] leading-relaxed break-words"
            style={{ color: turn.isFinal ? "rgba(232,234,240,0.92)" : "rgba(200,206,220,0.78)" }}
          >
            {turn.text}
            {!turn.isFinal && (
              <span className="ml-0.5 inline-block h-3 w-0.5 animate-pulse align-middle bg-[rgba(160,190,230,0.5)]" />
            )}
          </p>
        </div>
      </motion.div>
    );
  },
  (a, b) =>
    a.turn.id === b.turn.id &&
    a.turn.text === b.turn.text &&
    a.turn.isFinal === b.turn.isFinal &&
    a.turn.role === b.turn.role
);
