"""A/B benchmark: the REAL CombinedPipeline, same 100-frame video, same
config, only difference is TrackerConfig.detection_stride (A=1 i.e. current
behavior, B=3 i.e. optimized). Reports speed AND accuracy side by side so a
speedup can never be reported without also showing whether Target ID /
ANPR results held up.
"""
from __future__ import annotations

import time
from pathlib import Path

from backend.config import REPO_ROOT, AnprConfig, TrackerConfig
from backend.orchestrator import CombinedPipeline, OrchestratorRequest

PERSON_VIDEO = REPO_ROOT / "uploads" / "bench100_person.mp4"
ANPR_VIDEO = REPO_ROOT / "uploads" / "bench100_anpr.mp4"
REF_PHOTO = REPO_ROOT / "references" / "smoke_target" / "ref1.jpg"


def run_person(stride: int, label: str):
    tracker_cfg = TrackerConfig(detection_stride=stride)
    req = OrchestratorRequest(
        enable_person_id=True, reference_photo_paths=[REF_PHOTO],
        enable_behavior=True, tracker_config=tracker_cfg,
    )
    out_path = REPO_ROOT / "outputs" / f"_ab_person_{label}.mp4"
    t0 = time.perf_counter()
    result = CombinedPipeline(req).run(PERSON_VIDEO, out_path)
    elapsed = time.perf_counter() - t0
    out_path.unlink(missing_ok=True)
    return {
        "label": label, "stride": stride, "elapsed_sec": round(elapsed, 2),
        "fps": round(result.video_info.frame_count / elapsed, 2),
        "confirmed": result.person_id["confirmed"], "target_track_id": result.person_id["target_track_id"],
        "visible_frame_count": result.person_id["visible_frame_count"],
        "first_seen_sec": result.person_id["first_seen_sec"], "last_seen_sec": result.person_id["last_seen_sec"],
        "event_count": len(result.events),
        "behavior_event_counts": result.behavior["event_counts"] if result.behavior else {},
    }


def run_anpr(stride: int, label: str):
    tracker_cfg = TrackerConfig(detection_stride=stride)
    req = OrchestratorRequest(
        enable_anpr=True, target_plate="TEST123",
        anpr_config=AnprConfig(), tracker_config=tracker_cfg,
    )
    out_path = REPO_ROOT / "outputs" / f"_ab_anpr_{label}.mp4"
    t0 = time.perf_counter()
    result = CombinedPipeline(req).run(ANPR_VIDEO, out_path)
    elapsed = time.perf_counter() - t0
    out_path.unlink(missing_ok=True)
    detected = [{"text": d["text"], "confidence": d["mean_confidence"], "confirmed": d["confirmed"]} for d in result.anpr["detected_plates"]]
    return {
        "label": label, "stride": stride, "elapsed_sec": round(elapsed, 2),
        "fps": round(result.video_info.frame_count / elapsed, 2),
        "target_found": result.anpr["target"]["found"] if result.anpr["target"] else None,
        "match_confidence": result.anpr["target"]["match_confidence"] if result.anpr["target"] else None,
        "detected_plates": detected,
        "event_count": len(result.events),
        "plate_confirmed_events": sum(1 for e in result.events if e["type"] == "PLATE_CONFIRMED"),
    }


def print_row(a, b, key, fmt=str):
    va, vb = a.get(key), b.get(key)
    print(f"  {key:<24} A={fmt(va):<30} B={fmt(vb)}")


if __name__ == "__main__":
    print("=" * 70)
    print("PERSON VIDEO (100 frames) - Target Person ID + Behavior")
    print("=" * 70)
    a = run_person(stride=1, label="A_stride1")
    b = run_person(stride=3, label="B_stride3")
    for k in ["elapsed_sec", "fps", "confirmed", "target_track_id", "visible_frame_count",
              "first_seen_sec", "last_seen_sec", "event_count", "behavior_event_counts"]:
        print_row(a, b, k)
    speedup = a["elapsed_sec"] / b["elapsed_sec"] if b["elapsed_sec"] else float("inf")
    print(f"  {'SPEEDUP':<24} {speedup:.2f}x")

    print("\n" + "=" * 70)
    print("ANPR VIDEO (100 frames) - Plate Search 'TEST123'")
    print("=" * 70)
    a2 = run_anpr(stride=1, label="A_stride1")
    b2 = run_anpr(stride=3, label="B_stride3")
    for k in ["elapsed_sec", "fps", "target_found", "match_confidence", "detected_plates",
              "event_count", "plate_confirmed_events"]:
        print_row(a2, b2, k)
    speedup2 = a2["elapsed_sec"] / b2["elapsed_sec"] if b2["elapsed_sec"] else float("inf")
    print(f"  {'SPEEDUP':<24} {speedup2:.2f}x")
