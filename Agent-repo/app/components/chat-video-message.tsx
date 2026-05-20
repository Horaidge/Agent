"use client";

import { motion } from "framer-motion";
import type { VideoCaseKey } from "@/types/voice";
import { VIDEO_LABELS, VIDEO_MAP } from "@/lib/video-case-map";

interface ChatVideoMessageProps {
  video: VideoCaseKey;
}

export function ChatVideoMessage({ video }: ChatVideoMessageProps) {
  const src = VIDEO_MAP[video];
  const meta = VIDEO_LABELS[video];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
      className="flex justify-start"
    >
      <div
        className="w-full max-w-[96%] rounded-2xl rounded-bl-md border p-2.5"
        style={{
          background: "rgba(28, 32, 44, 0.65)",
          border: "1px solid rgba(90,140,180,0.15)",
          boxShadow: "0 8px 24px -14px rgba(20,40,60,0.4)",
        }}
      >
        <p
          className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em]"
          style={{ color: "rgba(130,200,220,0.65)" }}
        >
          Макс · Dzen.AI
        </p>

        <div className="overflow-hidden rounded-xl border" style={{ borderColor: "rgba(255,255,255,0.08)" }}>
          <div className="w-full bg-black/30" style={{ aspectRatio: "16/9" }}>
            <video
              src={src}
              controls
              playsInline
              preload="metadata"
              className="h-full w-full object-cover"
              aria-label={meta.title}
            />
          </div>
        </div>

        <p className="mt-2 text-[12px] leading-relaxed" style={{ color: "rgba(232,234,240,0.82)" }}>
          {meta.title}
        </p>
        <p className="text-[11px] leading-relaxed" style={{ color: "rgba(170,178,198,0.65)" }}>
          {meta.description}
        </p>
      </div>
    </motion.div>
  );
}
