import type { VideoItem } from "@/types/voice";

/**
 * Local video registry.
 * Videos are NOT shown in a UI catalog — they are opened exclusively
 * via tool-call events from the AI agent (show_video / hide_video).
 *
 * Structure is intentionally ready for a large registry (100+ items).
 */
const VIDEO_REGISTRY: VideoItem[] = [
  {
    id: "intro-001",
    title: "Добро пожаловать",
    description: "Краткое введение в возможности голосового агента.",
    thumbnail: "",
    videoUrl: "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    tags: ["intro", "welcome"],
    duration: "1:32",
  },
  {
    id: "demo-002",
    title: "Демонстрация функций",
    description: "Обзор ключевых возможностей платформы.",
    thumbnail: "",
    videoUrl: "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
    tags: ["demo", "features"],
    duration: "2:14",
  },
  {
    id: "tutorial-003",
    title: "Быстрый старт",
    description: "Пошаговый гайд для начала работы.",
    thumbnail: "",
    videoUrl: "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    tags: ["tutorial", "onboarding"],
    duration: "0:59",
  },
  {
    id: "case-004",
    title: "Кейс: автоматизация",
    description: "Пример автоматизации рабочего процесса с голосовым агентом.",
    thumbnail: "",
    videoUrl: "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
    tags: ["case", "automation"],
    duration: "3:05",
  },
  {
    id: "faq-005",
    title: "Частые вопросы",
    description: "Ответы на наиболее частые вопросы пользователей.",
    thumbnail: "",
    videoUrl: "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
    tags: ["faq"],
    duration: "1:48",
  },
];

/** Indexed map for O(1) lookup by id */
const VIDEO_MAP = new Map<string, VideoItem>(
  VIDEO_REGISTRY.map((item) => [item.id, item])
);

/**
 * Look up a video by its id.
 * Returns undefined if the id is not found — callers must handle this case.
 */
export function getVideoById(id: string): VideoItem | undefined {
  return VIDEO_MAP.get(id);
}

export { VIDEO_REGISTRY };
