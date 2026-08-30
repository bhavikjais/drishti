"""Small controlled smoke test for the Zone Intrusion pipeline against a real
video: reuses the Phase 1 person-ID fixture (uploads/smoke_person_id.mp4- a
real 3s/180-frame clip of a man walking rightward across frame, with other
pedestrians also present for a real multi-track scene) with a vertical zone
band positioned in his walking path, so a real ENTRY (and hopefully EXIT/
DWELL) can be observed, not just asserted from synthetic data.
"""
import json
from pathlib import Path

from backend.config import REPO_ROOT, ZoneConfig
from backend.modules.zone.geometry import Zone
from backend.modules.zone.pipeline import ZonePipeline

VIDEO = REPO_ROOT / "uploads" / "smoke_person_id.mp4"  # 960x540, 60fps, 180 frames

if __name__ == "__main__":
    zone = Zone(
        zone_id="smoke-zone-1", video_id="smoke_person_id", label="RESTRICTED ZONE",
        shape="rectangle", points=[(550 / 960, 0.0), (850 / 960, 1.0)],
    )
    config = ZoneConfig(entry_grace_frames=3, exit_grace_frames=15, track_absence_grace_frames=45, dwell_threshold_sec=0.5)
    output_path = REPO_ROOT / "outputs" / "smoke_zone_intrusion.mp4"

    def report_progress(p):
        pass

    result = ZonePipeline(config=config).run(VIDEO, zone, output_path, progress_cb=report_progress)

    summary = {
        "zone_id": result.zone_id,
        "tracks_observed": result.tracks_observed,
        "entries": result.entries,
        "exits": result.exits,
        "dwell_events": result.dwell_events,
        "codec_used": result.codec_used,
        "browser_playable": result.browser_playable,
        "video_info": {
            "fps": result.video_info.fps, "width": result.video_info.width,
            "height": result.video_info.height, "frame_count": result.video_info.frame_count,
            "duration_sec": round(result.video_info.duration_sec, 2),
        },
        "metrics": result.metrics,
        "track_summaries": [ts.__dict__ for ts in result.track_summaries],
    }
    print(json.dumps(summary, indent=2))

    print("\n=== EVENTS ===")
    for e in result.events:
        print(" ", e)

    print("\n=== PASS/FAIL CHECKS ===")
    checks = [
        ("at least one track observed", result.tracks_observed > 0),
        ("at least one ZONE_ENTRY fired", result.entries > 0),
        ("full frame count processed (no cap)", result.metrics["frames_read"] == result.video_info.frame_count),
        ("output fps preserved", abs(result.video_info.fps - 60.0) < 0.5),
        ("output browser playable", result.browser_playable),
        ("no event spam (events <= 3 per track roughly)", len(result.events) <= max(3, result.tracks_observed * 3)),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
