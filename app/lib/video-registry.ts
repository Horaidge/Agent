import type { VideoItem } from "@/types/voice";
import { VIDEO_LABELS, VIDEO_MAP } from "@/lib/video-case-map";

/**
 * Реестр демо-видео для инструментов show_video / hide_video (Vapi).
 * Файлы кладите в public/videos/ — в браузере URL вида /videos/dzen-01.mp4
 */
const VIDEO_REGISTRY: VideoItem[] = (Object.keys(VIDEO_MAP) as Array<keyof typeof VIDEO_MAP>).map((key) => ({
  id: key,
  title: VIDEO_LABELS[key].title,
  description: VIDEO_LABELS[key].description,
  thumbnail: "",
  videoUrl: VIDEO_MAP[key],
  tags: ["case", "demo", key],
  duration: "—",
}));

const VIDEO_MAP = new Map<string, VideoItem>(VIDEO_REGISTRY.map((item) => [item.id, item]));

export function getVideoById(id: string): VideoItem | undefined {
  return VIDEO_MAP.get(id);
}

export { VIDEO_REGISTRY };
