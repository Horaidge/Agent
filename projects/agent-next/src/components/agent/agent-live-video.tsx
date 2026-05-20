"use client";

import { useEffect, useRef } from "react";

type AgentLiveVideoProps = {
  track: MediaStreamTrack | null | undefined;
};

export function AgentLiveVideo({ track }: AgentLiveVideoProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const node = videoRef.current;
    if (!node) return;

    if (!track) {
      node.srcObject = null;
      return;
    }

    const stream = new MediaStream([track]);
    node.srcObject = stream;
    void node.play().catch(() => {
      // Autoplay can fail until user gesture; controls remain available.
    });

    return () => {
      node.srcObject = null;
    };
  }, [track]);

  if (!track) return null;

  return (
    <div className="rounded-[var(--radius-default)] border border-[var(--color-border)] bg-black/30 p-3">
      <p className="mono mb-2 text-[10px] uppercase tracking-[0.16em] text-[var(--color-ash-gray)]">
        agent video stream
      </p>
      <video ref={videoRef} className="h-auto w-full rounded" autoPlay playsInline controls muted />
    </div>
  );
}
