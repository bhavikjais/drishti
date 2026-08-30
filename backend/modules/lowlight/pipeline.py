"""Standalone Low-Light Enhancement pipeline: analyzes every frame of an
uploaded video, enhances only the frames classified LOW_LIGHT (see
core.lowlight), and writes a complete output video - preserving fps,
resolution, and duration, matching every other module's contract.

No detection/tracking runs here by design: this module's job is purely
"look at footage, brighten only what's genuinely dark, produce a usable
output video" (per the original spec). Person-ID and ANPR have their own
opt-in lowlight_config parameter (see their pipeline.py files) for enhancing
frames immediately before detection in the same pass, rather than requiring
a separate enhance-then-reprocess step.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.config import LowLightConfig
from backend.core.lowlight import process_frame
from backend.core.output import OutputVideoWriter
from backend.core.video import VideoInfo, VideoReader


@dataclass
class LowLightResult:
    output_video_path: Path
    codec_used: str
    browser_playable: bool
    video_info: VideoInfo
    metrics: dict
    backend_configured: str
    total_frames: int
    low_light_frames: int
    enhanced_frames: int
    enhanced_percentage: float
    low_light_detected: bool
    enhancement_applied: bool
    total_enhancement_time_sec: float
    mean_enhancement_overhead_ms: float
    fallback_used: bool


class LowLightPipeline:
    def __init__(self, config: LowLightConfig | None = None):
        self.config = config or LowLightConfig()

    def run(
        self,
        video_path: str | Path,
        output_path: str | Path,
        progress_cb: Callable[[float], None] | None = None,
    ) -> LowLightResult:
        cfg = self.config
        low_light_count = 0
        enhanced_count = 0
        total_enhance_time = 0.0
        fallback_used = False

        with VideoReader(video_path) as reader:
            writer = OutputVideoWriter(output_path, reader.info)
            progress_stride = max(1, reader.info.frame_count // 100) if reader.info.frame_count else 30

            for frame in reader:
                t0 = time.perf_counter()
                output_image, info = process_frame(frame.image, cfg)
                elapsed = time.perf_counter() - t0

                if info.classification == "LOW_LIGHT":
                    low_light_count += 1
                if info.enhanced:
                    enhanced_count += 1
                    total_enhance_time += elapsed
                    if info.fallback_reason:
                        fallback_used = True

                writer.write(output_image)
                if progress_cb is not None and (frame.index % progress_stride == 0) and reader.info.frame_count:
                    progress_cb(min(1.0, frame.index / reader.info.frame_count))

            writer.close()
            reader.metrics.frames_written = writer.frames_written
            metrics = reader.metrics.as_dict()
            video_info = reader.info

        if progress_cb is not None:
            progress_cb(1.0)

        total_frames = video_info.frame_count
        pct = round(100.0 * enhanced_count / total_frames, 2) if total_frames else 0.0
        mean_overhead_ms = round(1000.0 * total_enhance_time / enhanced_count, 3) if enhanced_count else 0.0

        return LowLightResult(
            output_video_path=Path(output_path),
            codec_used=writer.open_result.codec_used,
            browser_playable=writer.open_result.browser_playable,
            video_info=video_info,
            metrics=metrics,
            backend_configured=cfg.backend,
            total_frames=total_frames,
            low_light_frames=low_light_count,
            enhanced_frames=enhanced_count,
            enhanced_percentage=pct,
            low_light_detected=low_light_count > 0,
            enhancement_applied=enhanced_count > 0,
            total_enhancement_time_sec=round(total_enhance_time, 3),
            mean_enhancement_overhead_ms=mean_overhead_ms,
            fallback_used=fallback_used,
        )
