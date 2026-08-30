"""Real-video smoke test for Low-Light Enhancement.

Three parts:
  1. Standalone LowLightPipeline on a real genuinely-dark night-vision clip
     (uploads/smoke_lowlight_real_dark.mp4, trimmed from real footage) -
     verifies detection + enhancement + output video on real dark footage.
  2. Person-ID ablation: the same real pedestrian clip from Phase 1,
     synthetically darkened (uploads/smoke_person_id_dark.mp4), run WITHOUT
     then WITH lowlight enhancement - proves enhancement actually recovers
     target confirmation that fails (or is worse) in the dark without it.
  3. ANPR ablation: same idea with the real TEST123 plate clip, darkened -
     proves OCR recovers the plate text with enhancement, comparing
     before/after as the task requires.
"""
import json
import time
from pathlib import Path

from backend.config import REPO_ROOT, LowLightConfig
from backend.modules.anpr.pipeline import AnprPipeline
from backend.modules.lowlight.pipeline import LowLightPipeline
from backend.modules.person_id.pipeline import PersonIDPipeline

UPLOADS = REPO_ROOT / "uploads"
OUTPUTS = REPO_ROOT / "outputs"


def part1_standalone_real_dark_video():
    print("\n" + "=" * 70)
    print("PART 1: standalone LowLightPipeline on REAL dark night-vision clip")
    print("=" * 70)
    video = UPLOADS / "smoke_lowlight_real_dark.mp4"
    output = OUTPUTS / "smoke_lowlight_real_dark_enhanced.mp4"
    t0 = time.monotonic()
    result = LowLightPipeline().run(video, output)
    elapsed = time.monotonic() - t0
    summary = {
        "total_frames": result.total_frames, "low_light_frames": result.low_light_frames,
        "enhanced_frames": result.enhanced_frames, "enhanced_percentage": result.enhanced_percentage,
        "low_light_detected": result.low_light_detected, "enhancement_applied": result.enhancement_applied,
        "backend_configured": result.backend_configured, "fallback_used": result.fallback_used,
        "total_enhancement_time_sec": result.total_enhancement_time_sec,
        "mean_enhancement_overhead_ms": result.mean_enhancement_overhead_ms,
        "codec_used": result.codec_used, "browser_playable": result.browser_playable,
        "video_info": {"fps": result.video_info.fps, "width": result.video_info.width,
                        "height": result.video_info.height, "frame_count": result.video_info.frame_count},
        "metrics": result.metrics, "wall_clock_sec": round(elapsed, 2),
    }
    print(json.dumps(summary, indent=2))
    return summary


def part2_person_id_ablation():
    print("\n" + "=" * 70)
    print("PART 2: Person-ID ablation - dark video WITHOUT vs WITH enhancement")
    print("=" * 70)
    video_dark = UPLOADS / "smoke_person_id_dark.mp4"
    ref = [REPO_ROOT / "references" / "smoke_target" / "ref1.jpg"]

    print("\n-- 2a) dark input, enhancement DISABLED --")
    t0 = time.monotonic()
    r_off = PersonIDPipeline().run(video_dark, ref, OUTPUTS / "smoke_lowlight_personid_dark_off.mp4")
    t_off = time.monotonic() - t0
    print(json.dumps({
        "confirmed": r_off.confirmed, "target_track_id": r_off.target_track_id,
        "visible_frame_count": r_off.visible_frame_count, "wall_clock_sec": round(t_off, 2),
    }, indent=2))

    print("\n-- 2b) dark input, enhancement ENABLED --")
    t0 = time.monotonic()
    r_on = PersonIDPipeline().run(
        video_dark, ref, OUTPUTS / "smoke_lowlight_personid_dark_on.mp4",
        lowlight_config=LowLightConfig(),
    )
    t_on = time.monotonic() - t0
    print(json.dumps({
        "confirmed": r_on.confirmed, "target_track_id": r_on.target_track_id,
        "visible_frame_count": r_on.visible_frame_count,
        "lowlight_stats": r_on.lowlight_stats, "wall_clock_sec": round(t_on, 2),
    }, indent=2))

    return {
        "without_enhancement": {"confirmed": r_off.confirmed, "visible_frame_count": r_off.visible_frame_count, "wall_clock_sec": round(t_off, 2)},
        "with_enhancement": {"confirmed": r_on.confirmed, "visible_frame_count": r_on.visible_frame_count, "lowlight_stats": r_on.lowlight_stats, "wall_clock_sec": round(t_on, 2)},
    }


def part3_anpr_ablation():
    print("\n" + "=" * 70)
    print("PART 3: ANPR ablation - dark plate video WITHOUT vs WITH enhancement")
    print("=" * 70)
    video_dark = UPLOADS / "smoke_anpr_test123_dark.mp4"

    print("\n-- 3a) dark input, enhancement DISABLED --")
    t0 = time.monotonic()
    r_off = AnprPipeline().run(video_dark, OUTPUTS / "smoke_lowlight_anpr_dark_off.mp4", target_plate="TEST123")
    t_off = time.monotonic() - t0
    print(json.dumps({
        "target_found": r_off.target.found if r_off.target else None,
        "detected_plates": [d.__dict__ for d in r_off.detected_plates],
        "wall_clock_sec": round(t_off, 2),
    }, indent=2))

    print("\n-- 3b) dark input, enhancement ENABLED --")
    t0 = time.monotonic()
    r_on = AnprPipeline().run(
        video_dark, OUTPUTS / "smoke_lowlight_anpr_dark_on.mp4", target_plate="TEST123",
        lowlight_config=LowLightConfig(),
    )
    t_on = time.monotonic() - t0
    print(json.dumps({
        "target_found": r_on.target.found if r_on.target else None,
        "detected_plates": [d.__dict__ for d in r_on.detected_plates],
        "lowlight_stats": r_on.lowlight_stats, "wall_clock_sec": round(t_on, 2),
    }, indent=2))

    return {
        "without_enhancement": {"found": r_off.target.found if r_off.target else None, "plates": [d.text for d in r_off.detected_plates]},
        "with_enhancement": {"found": r_on.target.found if r_on.target else None, "plates": [d.text for d in r_on.detected_plates], "lowlight_stats": r_on.lowlight_stats},
    }


if __name__ == "__main__":
    p1 = part1_standalone_real_dark_video()
    p2 = part2_person_id_ablation()
    p3 = part3_anpr_ablation()

    print("\n" + "=" * 70)
    print("PASS/FAIL CHECKS")
    print("=" * 70)
    checks = [
        ("real dark video classified low-light", p1["low_light_detected"]),
        ("real dark video was enhanced", p1["enhancement_applied"]),
        ("full frame count processed (no cap)", p1["metrics"]["frames_read"] == p1["video_info"]["frame_count"]),
        ("standalone output browser playable", p1["browser_playable"]),
        ("fast backend used (no forced zero_dce)", p1["backend_configured"] == "fast" and not p1["fallback_used"]),
        ("person-id: enhancement was applied on dark video", p2["with_enhancement"]["lowlight_stats"]["enhancement_applied"]),
        ("person-id: WITH enhancement confirms target (WITHOUT may not)", p2["with_enhancement"]["confirmed"]),
        ("anpr: enhancement was applied on dark video", p3["with_enhancement"]["lowlight_stats"]["enhancement_applied"]),
        ("anpr: WITH enhancement finds TEST123 (WITHOUT may not)", p3["with_enhancement"]["found"]),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    print("\n=== SUMMARY: without vs with enhancement ===")
    print("Person-ID confirmed: without =", p2["without_enhancement"]["confirmed"], " | with =", p2["with_enhancement"]["confirmed"])
    print("ANPR target found:   without =", p3["without_enhancement"]["found"], " | with =", p3["with_enhancement"]["found"])
