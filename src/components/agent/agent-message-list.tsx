"use client";

import { useEffect, useState } from "react";
import type { AgentChatMessage } from "@/components/agent/types";
import { parseVideoToolMessage, type VideoToolMessagePayload } from "@/shared/video-tool-message";

type AgentMessageListProps = {
  messages: AgentChatMessage[];
};

export function AgentMessageList({ messages }: AgentMessageListProps) {
  const [activeVideo, setActiveVideo] = useState<VideoToolMessagePayload | null>(null);

  const visibleMessages = messages.filter((message) => {
    const videoPayload = parseVideoToolMessage(message.content);
    if (videoPayload) return true;
    return message.content.trim().length > 0;
  });

  useEffect(() => {
    if (!activeVideo) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setActiveVideo(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [activeVideo]);

  if (visibleMessages.length === 0) {
    return (
      <div className="rounded-[var(--radius-default)] border border-dashed border-[var(--color-border)] px-3 py-4 text-sm text-[var(--color-ash-gray)]">
        Диалог появится здесь после начала сессии и первых реплик.
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {visibleMessages.map((message) => {
        const isUser = message.role === "user";
        const isSystem = message.role === "system";
        const videoPayload = parseVideoToolMessage(message.content);
        const posterCandidate = videoPayload?.src.replace(/\.mp4(\?.*)?$/i, ".jpg");
        return (
          <div
            key={message.id}
            className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
          >
            <article
              className={`min-w-0 max-w-[82%] rounded-2xl border px-3 py-2 text-sm md:max-w-[76%] ${
                isUser
                  ? "border-[rgba(231,197,154,0.45)] bg-[linear-gradient(135deg,rgba(231,197,154,0.12),rgba(30,24,18,0.35))]"
                  : "border-[rgba(255,255,255,0.08)] bg-[linear-gradient(145deg,rgba(255,255,255,0.06),rgba(23,24,31,0.8))]"
              }`}
            >
            {videoPayload ? (
              <div className="space-y-2">
                <p className="text-xs text-[var(--color-ash-gray)]">
                  {videoPayload.title ?? `Video ${videoPayload.videoKey}`}
                </p>
                <button
                  type="button"
                  onClick={() => setActiveVideo(videoPayload)}
                  className="group relative block w-full overflow-hidden rounded-[var(--radius-default)] border border-[var(--color-border)] bg-black text-left transition-all hover:border-[var(--color-amber-glow)] hover:shadow-[0_0_20px_rgba(231,197,154,0.18)]"
                >
                  <div className="relative aspect-video min-h-[11.5rem] w-full md:min-h-[12.5rem]">
                    <video
                      preload="metadata"
                      playsInline
                      muted
                      poster={posterCandidate}
                      className="h-full w-full bg-black object-contain opacity-90 transition-opacity group-hover:opacity-100"
                      src={videoPayload.src}
                      onLoadedData={(event) => {
                        const video = event.currentTarget;
                        if (!Number.isFinite(video.duration) || video.duration <= 0) return;
                        if (video.currentTime < 0.05) {
                          video.currentTime = Math.min(0.05, video.duration);
                        }
                      }}
                    />
                    <div className="pointer-events-none absolute inset-0 bg-black/24" />
                    <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                      <span className="flex h-12 w-12 items-center justify-center rounded-full border border-[var(--color-border)] bg-black/55 text-lg text-[var(--color-polar-white)] shadow-[0_0_16px_rgba(0,0,0,0.45)]">
                        ▶
                      </span>
                    </div>
                    <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between bg-gradient-to-t from-black/75 via-black/20 to-transparent p-3">
                      <span className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-polar-white)]">
                        Preview
                      </span>
                      <span className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-amber-glow)]">
                        Open Fullscreen
                      </span>
                    </div>
                  </div>
                </button>
                {videoPayload.reason && isSystem ? (
                  <p className="text-xs text-[var(--color-ash-gray)]">{videoPayload.reason}</p>
                ) : null}
              </div>
            ) : (
                <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{message.content}</p>
            )}
            </article>
          </div>
        );
      })}

      {activeVideo ? (
        <div
          className="fixed inset-0 z-[90] flex items-center justify-center bg-black/90 p-4"
          onClick={() => setActiveVideo(null)}
        >
          <div
            className="relative w-full max-w-[90vw] rounded-xl border border-[var(--color-border)] bg-[var(--color-midnight-void)] p-3 md:p-4"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setActiveVideo(null)}
              className="mono absolute right-3 top-3 rounded border border-[var(--color-border)] px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-[var(--color-polar-white)] hover:border-[var(--color-amber-glow)]"
            >
              close
            </button>
            <p className="mb-3 pr-16 text-sm text-[var(--color-ash-gray)]">
              {activeVideo.title ?? `Video ${activeVideo.videoKey}`}
            </p>
            <video
              controls
              autoPlay
              playsInline
              preload="metadata"
              className="aspect-video max-h-[85vh] w-full rounded border border-[var(--color-border)] bg-black object-contain"
              src={activeVideo.src}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
