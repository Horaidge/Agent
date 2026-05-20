export const VIDEO_TOOL_MESSAGE_PREFIX = "__VIDEO_TOOL__:";

export type VideoToolMessagePayload = {
  videoKey: string;
  src: string;
  title?: string;
  reason?: string;
  startSeconds?: number;
};

export function buildVideoToolMessage(payload: VideoToolMessagePayload): string {
  return `${VIDEO_TOOL_MESSAGE_PREFIX}${JSON.stringify(payload)}`;
}

export function parseVideoToolMessage(content: string): VideoToolMessagePayload | null {
  if (!content.startsWith(VIDEO_TOOL_MESSAGE_PREFIX)) return null;
  const raw = content.slice(VIDEO_TOOL_MESSAGE_PREFIX.length);
  try {
    const parsed = JSON.parse(raw) as Partial<VideoToolMessagePayload>;
    if (!parsed || typeof parsed !== "object") return null;
    if (typeof parsed.videoKey !== "string" || typeof parsed.src !== "string") return null;
    return {
      videoKey: parsed.videoKey,
      src: parsed.src,
      title: typeof parsed.title === "string" ? parsed.title : undefined,
      reason: typeof parsed.reason === "string" ? parsed.reason : undefined,
      startSeconds: typeof parsed.startSeconds === "number" ? parsed.startSeconds : undefined,
    };
  } catch {
    return null;
  }
}
