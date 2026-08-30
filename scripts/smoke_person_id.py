"""Small controlled smoke test for the PersonID pipeline against a real
(but short, 180-frame) video clip with known ground truth:
uploads/smoke_person_id.mp4 contains a real pedestrian who is the same
person cropped into references/smoke_target/ref{1,2}.jpg.

Not a pytest test (deliberately) - this is the "run it for real and look at
the output" smoke check the task asked for, kept small and controlled
rather than a huge full-video run.
"""
import json
import time
from pathlib import Path

from backend.config import REPO_ROOT
from backend.modules.person_id.pipeline import PersonIDPipeline

VIDEO = REPO_ROOT / "uploads" / "smoke_person_id.mp4"
TARGET_REFS = [
    REPO_ROOT / "references" / "smoke_target" / "ref1.jpg",
    REPO_ROOT / "references" / "smoke_target" / "ref2.jpg",
]
UNRELATED_REF = [REPO_ROOT / "references" / "smoke_unrelated" / "ref1.jpg"]


def run_case(name, reference_photos, output_name):
    print(f"\n=== {name} ===")
    pipeline = PersonIDPipeline()
    output_path = REPO_ROOT / "outputs" / output_name
    snapshot_path = REPO_ROOT / "outputs" / f"{output_name}.snapshot.jpg"
    t0 = time.monotonic()
    result = pipeline.run(VIDEO, reference_photos, output_path, snapshot_path=snapshot_path)
    elapsed = time.monotonic() - t0

    summary = {
        "confirmed": result.confirmed,
        "target_track_id": result.target_track_id,
        "first_seen_sec": result.first_seen_sec,
        "last_seen_sec": result.last_seen_sec,
        "visible_duration_sec": result.visible_duration_sec,
        "visible_frame_count": result.visible_frame_count,
        "reference_usable_count": result.reference_usable_count,
        "reference_rejected": [str(p) for p, _ in result.reference_rejected],
        "min_reference_votes_used": result.min_reference_votes_used,
        "codec_used": result.codec_used,
        "browser_playable": result.browser_playable,
        "video_info": {
            "fps": result.video_info.fps,
            "width": result.video_info.width,
            "height": result.video_info.height,
            "frame_count": result.video_info.frame_count,
            "duration_sec": round(result.video_info.duration_sec, 2),
        },
        "metrics": result.metrics,
        "events": result.events,
        "snapshot_saved": result.snapshot_path is not None,
        "output_video_path": str(result.output_video_path),
        "wall_clock_sec": round(elapsed, 2),
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    r1 = run_case("single reference photo, target present", [TARGET_REFS[0]], "smoke_person_id_single_ref.mp4")
    r2 = run_case("multiple reference photos, target present", TARGET_REFS, "smoke_person_id_multi_ref.mp4")
    r3 = run_case("target NOT present (unrelated reference)", UNRELATED_REF, "smoke_person_id_not_present.mp4")

    print("\n=== PASS/FAIL CHECKS ===")
    checks = [
        ("single-ref confirms target", r1["confirmed"] is True),
        ("single-ref visible frames > 0", r1["visible_frame_count"] > 0),
        ("single-ref used 1 vote (adapted)", r1["min_reference_votes_used"] == 1),
        ("multi-ref confirms target", r2["confirmed"] is True),
        ("multi-ref used 2 votes", r2["min_reference_votes_used"] == 2),
        ("unrelated reference does NOT confirm", r3["confirmed"] is False),
        ("output video full frame count (no 90-frame cap)", r1["metrics"]["frames_read"] == r1["video_info"]["frame_count"]),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
