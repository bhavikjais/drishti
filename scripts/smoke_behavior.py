"""Small controlled smoke test for Behavioral Analytics against a real
video: reuses the Phase 1 fixture (uploads/smoke_person_id.mp4, a real 3s
busy-pedestrian clip) plus the same zone band used in the Phase 3 smoke test
and the same target track id (#3, the person_id-locked track from Phase 1),
so this exercises real zone+behavior and target+behavior correlation, not
just synthetic data.

Thresholds are lowered from the 10s/900deg-per-video defaults so that real
(if modest) instances are observable within a 3-second clip - documented
honestly in the report, not presented as the production defaults.
"""
import json
from pathlib import Path

from backend.config import REPO_ROOT, BehaviorConfig
from backend.modules.behavior.pipeline import BehaviorPipeline
from backend.modules.zone.geometry import Zone

VIDEO = REPO_ROOT / "uploads" / "smoke_person_id.mp4"  # 960x540, 60fps, 180 frames

if __name__ == "__main__":
    zone = Zone(
        zone_id="behavior-smoke-zone", video_id="smoke_person_id", label="RESTRICTED ZONE",
        shape="rectangle", points=[(550 / 960, 0.0), (850 / 960, 1.0)],
    )
    config = BehaviorConfig(
        loitering_seconds=0.5, loitering_radius_px=40.0,
        direction_change_degrees=60.0, reversal_angle_degrees=110.0,
        speed_threshold_px_per_sec=300.0, acceleration_threshold_px_per_sec=250.0,
        reversal_count=2, reversal_window_sec=3.0, reversal_radius_px=80.0,
        behavior_cooldown_seconds=1.0, min_displacement_px=6.0, sample_interval_sec=0.1,
    )
    output_path = REPO_ROOT / "outputs" / "smoke_behavior.mp4"
    evidence_dir = REPO_ROOT / "outputs" / "behavior_evidence"

    result = BehaviorPipeline(config=config).run(
        VIDEO, output_path, zone=zone, target_track_id=3, evidence_dir=evidence_dir,
    )

    summary = {
        "tracks_observed": result.tracks_observed,
        "event_counts": result.event_counts,
        "codec_used": result.codec_used,
        "browser_playable": result.browser_playable,
        "video_info": {
            "fps": result.video_info.fps, "width": result.video_info.width,
            "height": result.video_info.height, "frame_count": result.video_info.frame_count,
            "duration_sec": round(result.video_info.duration_sec, 2),
        },
        "metrics": result.metrics,
    }
    print(json.dumps(summary, indent=2))

    print("\n=== EVENTS ===")
    for e in result.events:
        print(" ", e)

    evidence_files = sorted(evidence_dir.glob("*.jpg")) if evidence_dir.exists() else []
    print(f"\n=== EVIDENCE ({len(evidence_files)} files) ===")
    for f in evidence_files:
        print(" ", f.name)

    print("\n=== PASS/FAIL CHECKS ===")
    total_events = sum(result.event_counts.values())
    checks = [
        ("at least one track observed", result.tracks_observed > 0),
        ("at least one behavior event fired", total_events > 0),
        ("full frame count processed (no cap)", result.metrics["frames_read"] == result.video_info.frame_count),
        ("output fps preserved", abs(result.video_info.fps - 60.0) < 0.5),
        ("output browser playable", result.browser_playable),
        ("evidence files were saved", len(evidence_files) > 0),
        ("evidence count <= event count (not saved every frame)", len(evidence_files) <= total_events),
        ("no gross event spam (< 5 events per track on average)", total_events < max(5, result.tracks_observed * 5)),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
