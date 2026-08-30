import { api } from "./client";
import type { ReferenceUpload } from "./types";

export function uploadReferencePhotos(files: File[]): Promise<ReferenceUpload> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  return api.postForm<ReferenceUpload>("/api/references", form);
}
