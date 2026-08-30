"""Small controlled smoke test for the ANPR pipeline against a real (but
short, 150-frame / 5s) video with a known ground-truth plate: the vehicle in
uploads/smoke_anpr_test123.mp4 carries an overlaid "TEST123" plate, so
automatic OCR, correct search, and wrong search all have a known right
answer to check against.
"""
import json
import time
from pathlib import Path

from backend.config import REPO_ROOT
from backend.modules.anpr.pipeline import AnprPipeline

VIDEO = REPO_ROOT / "uploads" / "smoke_anpr_test123.mp4"


def run_case(name, target_plate, output_name):
    print(f"\n=== {name} ===")
    pipeline = AnprPipeline()
    output_path = REPO_ROOT / "outputs" / output_name
    t0 = time.monotonic()
    result = pipeline.run(VIDEO, output_path, target_plate=target_plate)
    elapsed = time.monotonic() - t0

    summary = {
        "mode": result.mode,
        "searched_plate": result.searched_plate,
        "vehicles_detected": result.vehicles_detected,
        "detected_plates": [d.__dict__ for d in result.detected_plates],
        "target": result.target.__dict__ if result.target else None,
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
        "ocr_status": result.ocr_status,
        "event_counts": {},
        "output_video_path": str(result.output_video_path),
        "wall_clock_sec": round(elapsed, 2),
    }
    from collections import Counter
    summary["event_counts"] = dict(Counter(e["type"] for e in result.events))
    print(json.dumps(summary, indent=2))
    return summary, result.events


if __name__ == "__main__":
    r1, ev1 = run_case("AUTOMATIC ANPR (no search)", None, "smoke_anpr_automatic.mp4")
    r2, ev2 = run_case("SEARCH correct plate TEST123", "TEST123", "smoke_anpr_search_correct.mp4")
    r3, ev3 = run_case("SEARCH wrong plate ZZZ999", "ZZZ999", "smoke_anpr_search_wrong.mp4")

    print("\n=== PASS/FAIL CHECKS ===")
    confirmed_texts = [d["text"] for d in r1["detected_plates"] if d["confirmed"]]
    checks = [
        ("automatic mode detects >=1 vehicle", r1["vehicles_detected"] >= 1),
        ("automatic mode confirms TEST123", "TEST123" in confirmed_texts),
        ("no PLATE_CONFIRMED event spam (<=vehicles_detected)", r1["event_counts"].get("PLATE_CONFIRMED", 0) <= r1["vehicles_detected"]),
        ("full frame count processed (no cap)", r1["metrics"]["frames_read"] == r1["video_info"]["frame_count"]),
        ("correct search: target found", r2["target"]["found"] is True),
        ("correct search: plate text is TEST123", r2["target"]["plate_text"] == "TEST123"),
        ("correct search: visible_frame_count > 0", r2["target"]["visible_frame_count"] > 0),
        ("correct search: TARGET_VEHICLE_FOUND fires once", r2["event_counts"].get("TARGET_VEHICLE_FOUND", 0) == 1),
        ("wrong search: target NOT found", r3["target"]["found"] is False),
        ("wrong search: no TARGET_VEHICLE_FOUND event", r3["event_counts"].get("TARGET_VEHICLE_FOUND", 0) == 0),
        ("wrong search: no false-positive track id", r3["target"]["track_id"] is None),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    print("\n=== EVENTS (correct search) ===")
    for e in ev2:
        print(" ", e)
