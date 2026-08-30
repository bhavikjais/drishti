import { Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { createZone } from "../../api/zones";
import { representativeFrameUrl } from "../../api/videos";
import { ApiError } from "../../api/client";
import type { Zone, ZoneShape } from "../../api/types";

type Point = [number, number];

export function ZoneDrawer({
  videoId,
  zones,
  onZonesChange,
}: {
  videoId: string;
  zones: Zone[];
  onZonesChange: (zones: Zone[]) => void;
}) {
  const [shape, setShape] = useState<ZoneShape>("polygon");
  const [points, setPoints] = useState<Point[]>([]);
  const [zoneName, setZoneName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  const canClose = shape === "polygon" && points.length >= 3;
  const rectReady = shape === "rectangle" && points.length === 2;

  function handleImageClick(e: React.MouseEvent<HTMLImageElement>) {
    const img = imgRef.current;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const nx = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const ny = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));

    if (shape === "rectangle") {
      if (points.length >= 2) {
        setPoints([[nx, ny]]);
      } else {
        setPoints((p) => [...p, [nx, ny]]);
      }
      return;
    }
    setPoints((p) => [...p, [nx, ny]]);
  }

  function resetDrawing() {
    setPoints([]);
    setZoneName("");
    setError(null);
  }

  async function saveZone() {
    const ready = shape === "rectangle" ? rectReady : canClose;
    if (!ready) return;
    setSaving(true);
    setError(null);
    try {
      const zone = await createZone({
        video_id: videoId,
        shape,
        points,
        label: zoneName.trim() || "Restricted Area",
      });
      onZonesChange([...zones, zone]);
      resetDrawing();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save zone");
    } finally {
      setSaving(false);
    }
  }

  function removeZone(zoneId: string) {
    onZonesChange(zones.filter((z) => z.zone_id !== zoneId));
  }

  const svgPolygon = (pts: Point[]) => pts.map(([x, y]) => `${x * 100},${y * 100}`).join(" ");

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex gap-1 rounded-md border border-border-2 bg-bg-3 p-1">
          {(["polygon", "rectangle"] as ZoneShape[]).map((s) => (
            <button
              key={s}
              onClick={() => {
                setShape(s);
                resetDrawing();
              }}
              className={`rounded px-3 py-1.5 text-[11.5px] font-semibold capitalize transition-colors ${
                shape === s ? "bg-accent-blue text-[#051020]" : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="text-[11px] text-text-tertiary">
          {shape === "polygon" ? "Click to add points, then close the polygon" : "Click two opposite corners"}
        </div>
      </div>

      <div className="relative inline-block w-full select-none overflow-hidden rounded-lg border border-border-1 bg-black">
        <img
          ref={imgRef}
          src={representativeFrameUrl(videoId)}
          alt="Representative frame"
          onClick={handleImageClick}
          className="block w-full cursor-crosshair"
          draggable={false}
        />
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full">
          {zones.map((z) => (
            <polygon
              key={z.zone_id}
              points={svgPolygon(z.shape === "rectangle" ? rectToQuad(z.points as Point[]) : (z.points as Point[]))}
              fill="rgba(245,166,35,0.08)"
              stroke="var(--color-accent-amber)"
              strokeWidth="0.4"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {points.length > 0 && (
            <polygon
              points={svgPolygon(shape === "rectangle" && points.length === 2 ? rectToQuad(points) : points)}
              fill="rgba(59,158,255,0.12)"
              stroke="var(--color-accent-blue)"
              strokeWidth="0.5"
              vectorEffect="non-scaling-stroke"
            />
          )}
          {points.map(([x, y], i) => (
            <circle key={i} cx={x * 100} cy={y * 100} r="0.8" fill="var(--color-accent-blue)" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        {zones.map((z) => {
          const [x, y] = z.shape === "rectangle" ? (z.points as Point[])[0] : (z.points as Point[])[0];
          return (
            <div
              key={z.zone_id}
              className="pointer-events-none absolute -translate-y-full rounded bg-accent-amber px-1.5 py-0.5 text-[10px] font-bold text-black"
              style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
            >
              {z.label}
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <input
          className="flex-1 rounded border border-border-2 bg-bg-3 px-3 py-2 text-[12.5px] text-text-primary placeholder:text-text-disabled focus:border-accent-blue focus:outline-none"
          placeholder="Zone name (e.g. Restricted Area)"
          value={zoneName}
          onChange={(e) => setZoneName(e.target.value)}
        />
        <button
          onClick={saveZone}
          disabled={!(shape === "rectangle" ? rectReady : canClose) || saving}
          className="rounded bg-accent-blue px-3 py-2 text-[12px] font-semibold text-[#051020] disabled:opacity-40"
        >
          {saving ? "Saving…" : shape === "polygon" ? "Close & Save Zone" : "Save Zone"}
        </button>
        {points.length > 0 && (
          <button onClick={resetDrawing} className="rounded border border-border-2 px-3 py-2 text-[12px] text-text-secondary hover:bg-bg-3">
            Reset
          </button>
        )}
      </div>
      {error && <div className="mt-2 text-[11.5px] text-accent-red">{error}</div>}

      {zones.length > 0 && (
        <div className="mt-4 flex flex-col gap-1.5">
          {zones.map((z) => (
            <div key={z.zone_id} className="flex items-center justify-between rounded border border-border-1 bg-bg-3 px-3 py-2">
              <div className="flex items-center gap-2 text-[12.5px] text-text-primary">
                <span className="h-2 w-2 rounded-full bg-accent-amber" />
                {z.label}
                <span className="text-[11px] text-text-tertiary capitalize">({z.shape})</span>
              </div>
              <button onClick={() => removeZone(z.zone_id)} className="text-text-tertiary hover:text-accent-red" title="Remove from this analysis">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function rectToQuad([[x1, y1], [x2, y2]]: Point[]): Point[] {
  return [
    [x1, y1],
    [x2, y1],
    [x2, y2],
    [x1, y2],
  ];
}
