"use client";

import { useCallback, useState } from "react";
import type { MediaState, VideoItem } from "@/types/voice";
import { getVideoById } from "@/lib/video-registry";

export function useMediaOverlay() {
  const [mediaState, setMediaState] = useState<MediaState>({
    activeVideo: null,
    isVideoOpen: false,
  });

  /**
   * Show video by id (triggered by agent tool-call: show_video).
   * Does NOT stop the voice call.
   */
  const showVideo = useCallback((videoId: string) => {
    const video: VideoItem | undefined = getVideoById(videoId);
    if (!video) {
      if (process.env.NODE_ENV === "development") {
        console.warn(`[v0] show_video: unknown videoId "${videoId}"`);
      }
      return;
    }
    setMediaState({ activeVideo: video, isVideoOpen: true });
  }, []);

  /**
   * Hide video (triggered by agent tool-call: hide_video or user close button).
   */
  const hideVideo = useCallback(() => {
    setMediaState({ activeVideo: null, isVideoOpen: false });
  }, []);

  return { mediaState, showVideo, hideVideo };
}
