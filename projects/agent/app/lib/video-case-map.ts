import type { VideoCaseKey } from "@/types/voice";

export const VIDEO_MAP: Record<VideoCaseKey, string> = {
  inspectra: "/videos/inspectra.mp4",
  anna: "/videos/anna.mp4",
  polevoy: "/videos/polevoy.mp4",
  metallica: "/videos/metallica.mp4",
};

export const VIDEO_LABELS: Record<VideoCaseKey, { title: string; description: string }> = {
  inspectra: {
    title: "Inspectra",
    description: "Аватар / визуальный AI",
  },
  anna: {
    title: "Anna",
    description: "Мультиагентная система",
  },
  polevoy: {
    title: "Иван Полевой / PhosAgro",
    description: "RAG / экспертная система",
  },
  metallica: {
    title: "Metallica",
    description: "Креативный demo-кейс",
  },
};

export function isVideoCaseKey(value: unknown): value is VideoCaseKey {
  return typeof value === "string" && value in VIDEO_MAP;
}
