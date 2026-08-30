"""Stage-by-stage performance benchmark of the real pipeline components on a
controlled 100-frame segment of real video - no synthetic data, no mocking.

Measures wall-clock time spent in each real call site (video decode, YOLO
detection+tracking, face detection, face recognition, plate detection, OCR,
low-light enhancement, drawing, video encoding) using the SAME classes the
orchestrator uses, wired together the same way, just with timing wrapped
around each stage. This file does not modify any production code - it's a
read-only diagnostic.
"""
from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

import cv2

from backend.config import (
    REPO_ROOT, TrackerConfig, YUNET_MODEL_PATH, SFACE_MODEL_PATH,
)
from backend.core.output import OutputVideoWriter, draw_target_box
from backend.core.tracker import ObjectTracker
from backend.core.video import VideoReader
from backend.modules.anpr.ocr import PlateOcr
from backend.modules.anpr.plate_detector import PlateDetector
from backend.modules.person_id.detector import FaceDetector
from backend.modules.person_id.recognizer import FaceRecognizer, ReferenceSet

N_FRAMES = 100

timings: dict[str, list[float]] = defaultdict(list)
counts: dict[str, int] = defaultdict(int)


@contextmanager
def stage(name: str):
    t0 = time.perf_counter()
    yield
    timings[name].append(time.perf_counter() - t0)
    counts[name] += 1


def report(title: str):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
    total = sum(sum(v) for v in timings.values())
    rows = []
    for name, vals in timings.items():
        s = sum(vals)
        rows.append((name, s, len(vals), s / len(vals) * 1000, s / total * 100 if total else 0))
    rows.sort(key=lambda r: -r[1])
    print(f"{'stage':<24}{'total_s':>10}{'calls':>8}{'avg_ms':>10}{'% of total':>12}")
    for name, s, n, avg_ms, pct in rows:
        print(f"{name:<24}{s:>10.3f}{n:>8}{avg_ms:>10.2f}{pct:>11.1f}%")
    print(f"{'TOTAL (measured)':<24}{total:>10.3f}")


def bench_person_video():
    """Person-heavy content: decode, YOLO(person+vehicle classes)+tracking,
    face detection/recognition (periodic), drawing, encoding."""
    global timings, counts
    timings = defaultdict(list)
    counts = defaultdict(int)

    video_path = REPO_ROOT / "uploads" / "smoke_person_id.mp4"
    ref_path = REPO_ROOT / "references" / "smoke_target" / "ref1.jpg"
    tracker_config = TrackerConfig()
    tracker = ObjectTracker(tracker_config, class_ids=(tracker_config.person_class_id, *tracker_config.vehicle_class_ids))
    face_detector = FaceDetector(YUNET_MODEL_PATH)
    face_recognizer = FaceRecognizer(SFACE_MODEL_PATH)
    reference_set = ReferenceSet([ref_path], face_detector, face_recognizer)
    out_path = REPO_ROOT / "outputs" / "_bench_person.mp4"

    with VideoReader(video_path) as reader:
        writer = OutputVideoWriter(out_path, reader.info)
        h, w = reader.info.height, reader.info.width
        it = iter(reader)
        for i in range(N_FRAMES):
            with stage("video_decode"):
                frame = next(it)

            with stage("yolo_detect_track"):
                tracks = tracker.update(frame.image)

            if i % 5 == 0:
                for t in tracks:
                    if t.class_id != tracker_config.person_class_id:
                        continue
                    x1, y1, x2, y2 = t.bbox
                    crop = frame.image[max(0, y1):y2, max(0, x1):x2]
                    if crop.size == 0:
                        continue
                    with stage("face_detect"):
                        face = face_detector.best(crop)
                    if face is None:
                        continue
                    with stage("face_recognize"):
                        emb = face_recognizer.embed(crop, face)
                    with stage("face_vote"):
                        reference_set.vote(emb, 0.42)

            with stage("drawing"):
                for t in tracks[:1]:
                    draw_target_box(frame.image, t.bbox, label="TARGET")

            with stage("video_encode"):
                writer.write(frame.image)

        writer.close()
    out_path.unlink(missing_ok=True)
    report(f"PERSON VIDEO ({N_FRAMES} frames, {w}x{h}, all-classes tracking + periodic face)")


def bench_anpr_video():
    """Vehicle-heavy content: decode, YOLO(vehicle classes)+tracking, plate
    detection, OCR, drawing, encoding."""
    global timings, counts
    timings = defaultdict(list)
    counts = defaultdict(int)

    video_path = REPO_ROOT / "uploads" / "smoke_anpr_test123.mp4"
    tracker_config = TrackerConfig()
    tracker = ObjectTracker(tracker_config, class_ids=tracker_config.vehicle_class_ids)
    plate_detector = PlateDetector()
    ocr = PlateOcr()
    out_path = REPO_ROOT / "outputs" / "_bench_anpr.mp4"

    with VideoReader(video_path) as reader:
        writer = OutputVideoWriter(out_path, reader.info)
        h, w = reader.info.height, reader.info.width
        it = iter(reader)
        for i in range(N_FRAMES):
            with stage("video_decode"):
                frame = next(it)

            with stage("yolo_detect_track"):
                tracks = tracker.update(frame.image)

            if i % 5 == 0:
                for t in tracks:
                    x1, y1, x2, y2 = t.bbox
                    crop = frame.image[max(0, y1):y2, max(0, x1):x2]
                    ch, cw = crop.shape[:2] if crop.size else (0, 0)
                    if cw < 100 or ch < 80:
                        continue
                    with stage("plate_locate"):
                        candidate = plate_detector.locate(crop)
                    if candidate is None:
                        continue
                    px1, py1, px2, py2 = candidate.bbox
                    with stage("ocr_read"):
                        ocr.read(crop[py1:py2, px1:px2])

            with stage("drawing"):
                for t in tracks[:1]:
                    draw_target_box(frame.image, t.bbox, label="TARGET")

            with stage("video_encode"):
                writer.write(frame.image)

        writer.close()
    out_path.unlink(missing_ok=True)
    report(f"ANPR VIDEO ({N_FRAMES} frames, {w}x{h}, vehicle tracking + periodic plate/OCR)")


if __name__ == "__main__":
    import torch
    print(f"torch threads={torch.get_num_threads()} cv2 threads={cv2.getNumThreads()} device=cpu")
    t0 = time.perf_counter()
    bench_person_video()
    print(f"\nwall clock: {time.perf_counter() - t0:.2f}s")

    t0 = time.perf_counter()
    bench_anpr_video()
    print(f"\nwall clock: {time.perf_counter() - t0:.2f}s")
