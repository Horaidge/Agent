"use client";

import { useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { VideoItem } from "@/types/voice";

interface VideoOverlayPlayerProps {
  video: VideoItem | null;
  isOpen: boolean;
  onClose: () => void;
}

export function VideoOverlayPlayer({ video, isOpen, onClose }: VideoOverlayPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  return (
    <AnimatePresence>
      {isOpen && video && (
        <motion.div
          key="video-player"
          className="w-full max-w-xl mx-auto px-4"
          initial={{ opacity: 0, y: -12, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -8, scale: 0.97 }}
          transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
        >
          <div
            className="relative overflow-hidden"
            style={{
              borderRadius: 20,
              background: "#0C0D14",
              border: "1px solid rgba(34, 211, 238, 0.15)",
              boxShadow:
                "0 8px 40px rgba(34, 211, 238, 0.08), 0 2px 12px rgba(0,0,0,0.6)",
            }}
          >
            {/* Video element — no autoplay to respect iOS constraints */}
            <div className="relative w-full" style={{ aspectRatio: "16/9" }}>
              <video
                ref={videoRef}
                className="w-full h-full object-cover"
                src={video.videoUrl}
                poster={video.thumbnail || undefined}
                controls
                playsInline
                preload="metadata"
                style={{ borderRadius: "20px 20px 0 0", display: "block" }}
                aria-label={video.title}
              />
            </div>

            {/* Info bar */}
            <div className="flex items-start justify-between px-4 py-3 gap-3">
              <div className="flex-1 min-w-0">
                <p
                  className="text-sm font-medium truncate leading-snug"
                  style={{ color: "rgba(232, 234, 240, 0.95)" }}
                >
                  {video.title}
                </p>
                {video.description && (
                  <p
                    className="text-xs mt-0.5 leading-relaxed line-clamp-2"
                    style={{ color: "rgba(232, 234, 240, 0.4)" }}
                  >
                    {video.description}
                  </p>
                )}
              </div>

              {/* Duration badge */}
              <span
                className="shrink-0 text-[10px] font-mono px-2 py-0.5 rounded-full"
                style={{
                  background: "rgba(34, 211, 238, 0.08)",
                  color: "rgba(34, 211, 238, 0.6)",
                  border: "1px solid rgba(34, 211, 238, 0.15)",
                }}
              >
                {video.duration}
              </span>
            </div>

            {/* Close button */}
            <button
              onClick={onClose}
              aria-label="Закрыть видео"
              className="absolute top-3 right-3 flex items-center justify-center rounded-full transition-opacity"
              style={{
                width: 28,
                height: 28,
                background: "rgba(5, 6, 10, 0.75)",
                backdropFilter: "blur(8px)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "rgba(232,234,240,0.7)",
              }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <line x1="1" y1="1" x2="11" y2="11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                <line x1="11" y1="1" x2="1" y2="11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
