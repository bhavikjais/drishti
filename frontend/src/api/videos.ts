import { api } from "./client";
import type { VideoUpload } from "./types";

export function uploadVideo(file: File): Promise<VideoUpload> {
  const form = new FormData();
  form.append("file", file);
  return api.postForm<VideoUpload>("/api/videos", form);
}

export function representativeFrameUrl(videoId: string, at = 0.5): string {
  return `/api/videos/${encodeURIComponent(videoId)}/frame?at=${at}`;
}
