import { AlertTriangle, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { uploadVideo } from "../../api/videos";
import { formatResolution } from "../../lib/format";
import type { VideoUpload } from "../../api/types";

export function UploadZone({ onUploaded }: { onUploaded: (video: VideoUpload, file: File) => void }) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setSelected(file);
    setUploading(true);
    setError(null);
    try {
      const result = await uploadVideo(file);
      onUploaded(result, file);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
      setSelected(null);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <div
        onClick={() => !uploading && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void handleFile(file);
        }}
        className={`cursor-pointer rounded-[10px] border-[1.5px] border-dashed px-6 py-16 text-center transition-colors ${
          dragOver ? "border-accent-blue bg-accent-blue/10" : "border-border-2 bg-bg-2 hover:border-accent-blue/60"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
        <UploadCloud size={34} className="mx-auto mb-3 text-text-tertiary" />
        {uploading ? (
          <>
            <div className="text-[15px] font-semibold text-text-primary">Uploading {selected?.name}…</div>
            <div className="mt-2 text-[11.5px] text-text-tertiary">Reading video metadata</div>
          </>
        ) : (
          <>
            <div className="text-[15px] font-semibold tracking-wide text-text-primary">DROP SURVEILLANCE VIDEO HERE</div>
            <div className="mt-2 text-[11.5px] text-text-tertiary">or click to browse files</div>
          </>
        )}
      </div>
      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-accent-red/35 bg-accent-red/10 px-3 py-2.5 text-[12px] text-accent-red">
          <AlertTriangle size={14} className="shrink-0" /> {error}
        </div>
      )}
    </div>
  );
}

export function VideoSummary({ filename, video }: { filename: string; video: VideoUpload["video_info"] }) {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2 text-[12.5px]">
      <Field label="Filename" value={filename} />
      <Field label="Duration" value={`${video.duration_sec.toFixed(1)}s`} />
      <Field label="Resolution" value={formatResolution(video.width, video.height)} />
      <Field label="FPS" value={video.fps.toFixed(1)} />
      <Field label="Frames" value={String(video.frame_count)} />
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className="mt-0.5 font-mono text-text-primary">{value}</div>
    </div>
  );
}
