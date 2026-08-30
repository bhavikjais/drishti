"""Central configuration: paths, device detection, per-module defaults.

All paths are resolved relative to the repo root (parent of backend/), so the
process can be launched from any working directory.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"
UPLOADS_DIR = REPO_ROOT / "uploads"
OUTPUTS_DIR = REPO_ROOT / "outputs"
REFERENCES_DIR = REPO_ROOT / "references"
ZONES_DIR = REPO_ROOT / "zones"
JOBS_DIR = REPO_ROOT / "jobs"
EVIDENCE_DIR = REPO_ROOT / "outputs" / "evidence"

for _d in (MODELS_DIR, UPLOADS_DIR, OUTPUTS_DIR, REFERENCES_DIR, ZONES_DIR, JOBS_DIR, EVIDENCE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

YUNET_MODEL_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"
YOLO_MODEL_PATH = MODELS_DIR / "yolov8n.pt"
OPENH264_DLL_PATH = MODELS_DIR / "openh264-1.8.0-win64.dll"
OSNET_MODEL_PATH = MODELS_DIR / "osnet_x0_25_msmt17.onnx"

LOG_LEVEL = logging.INFO


def detect_device() -> str:
    """Return 'cuda' if a usable GPU is present, else 'cpu'. Never raises."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


DEVICE = detect_device()


@dataclass
class VideoEngineConfig:
    # Codec fourcc candidates tried in order when opening the output writer.
    output_codec_candidates: tuple[str, ...] = ("avc1", "H264", "mp4v")


@dataclass
class TrackerConfig:
    model_path: Path = YOLO_MODEL_PATH
    device: str = DEVICE
    tracker_yaml: str = "bytetrack.yaml"
    confidence: float = 0.35
    iou: float = 0.5
    # COCO class ids this tracker instance restricts itself to.
    person_class_id: int = 0
    vehicle_class_ids: tuple[int, ...] = (2, 3, 5, 7)  # car, motorcycle, bus, truck

    # Run full YOLO+ByteTrack inference every Nth frame; on the frames in
    # between, track boxes are extrapolated from recent velocity instead of
    # re-running the model (see core.tracker.ObjectTracker). This is the
    # dominant cost in every pipeline (benchmarked ~75-90% of per-frame
    # time), so it's the highest-leverage performance knob in the system.
    # Default is 3: A/B-benchmarked on a real 150-frame ANPR search video
    # (uploads/smoke_anpr_test123.mp4) at 2.36x speedup (0.66 -> 1.56 FPS)
    # with identical search accuracy (same plate, same 100% confidence),
    # zero false LOST/REACQUIRED events, and a continuously stable red box
    # once locked -- see scripts/benchmark_ab.py. Pass detection_stride=1
    # explicitly (TrackerConfig(detection_stride=1)) for maximum-accuracy
    # runs where every frame should be truly detected, not propagated.
    detection_stride: int = 3


@dataclass
class PersonIDConfig:
    """Target-person identification & tracking configuration.

    min_reference_votes is a *ceiling* configured for the multi-reference
    case. The pipeline adapts it down (never up) to the number of usable
    reference photos actually available, so a single-reference upload never
    crashes or becomes unsatisfiable. See PersonIDConfig.resolve_votes().
    """

    similarity_threshold: float = 0.42
    min_reference_votes: int = 2
    # Number of separate matching observations (frames) required before a
    # track is promoted to CONFIRMED target.
    confirmation_observations: int = 2
    # Run face detection/recognition on person crops every N frames
    # (periodic sampling - the expensive step).
    face_sample_stride: int = 5
    # How many consecutive frames the target's track id may be absent before
    # we consider it "lost" and eligible for re-acquisition.
    gap_tolerance_frames: int = 45
    # How many consecutive frames of PURE Kalman prediction (no real
    # detection corroborating it) to keep drawing the box for. Deliberately
    # much shorter than gap_tolerance_frames: a linear-velocity prediction is
    # trustworthy for bridging a brief occlusion (someone walks in front of
    # the target for a few frames), but empirically drifts onto an unrelated
    # person's position after the target has genuinely left frame and isn't
    # coming back on that trajectory (measured on real footage: visible drift
    # by ~10 frames after last real detection). Beyond this window the box is
    # hidden (not fabricated) until the SAME track reappears or ReID/face
    # re-associates a new one -- gap_tolerance_frames still governs how long
    # that re-acquisition window stays open.
    max_prediction_frames: int = 12
    # Padding (fraction of bbox size) added around a person box when
    # cropping for face detection, since faces sit near the top of the box.
    crop_pad_frac: float = 0.15

    # --- Person ReID (BoT-SORT + OSNet) -- see backend/modules/person_id/person_reid.py ---
    # Run OSNet embedding on sampled person tracks every N frames -- like
    # face_sample_stride, this is the expensive step, run periodically not
    # every frame. Independent of face_sample_stride: ReID is what maintains
    # identity between face-recognition samples, so it typically wants a
    # shorter interval than face sampling.
    reid_sample_stride: int = 3
    # Minimum cosine similarity against the target's appearance gallery to
    # count as a ReID match. Empirically measured on real footage (this
    # project's own test video): same-person crops ~0.876, different-person
    # ~0.42-0.53 -- 0.65 sits well inside that gap.
    reid_similarity_threshold: float = 0.65
    # Bounded gallery size -- old embeddings age out rather than growing
    # forever, and a bounded gallery can't be dominated by one bad stretch.
    gallery_max_size: int = 30
    # Only add an observation to the target's appearance gallery when the
    # bbox is at least this many pixels on a side -- a tiny/distant crop's
    # embedding is unreliable and would risk polluting the gallery (identity
    # drift protection, section 12 of the plan).
    min_bbox_side_for_gallery: int = 60
    # Combined target score weights (section 13) -- configurable rather than
    # hardcoded so the balance between signals can be tuned without touching
    # pipeline code. Only face_weight/reid_weight are used for the
    # confirm/reacquire decision today; motion_weight/track_weight are
    # exposed for future use (e.g. penalizing a candidate whose track has
    # very little history) without a config/schema change later.
    face_weight: float = 0.6
    reid_weight: float = 0.4
    motion_weight: float = 0.0
    track_weight: float = 0.0

    @staticmethod
    def resolve_votes(configured_min_votes: int, usable_reference_count: int) -> int:
        """Adapt min_reference_votes to the number of usable references.

        - 0 usable references is a hard error, raised by the caller before
          this is even reached.
        - 1 usable reference -> 1 vote required (can't ask for 2 votes from
          1 reference).
        - >=2 usable references -> min(configured_min_votes, usable_count),
          preserving the intended multi-reference voting behavior.
        """
        if usable_reference_count <= 0:
            raise ValueError("resolve_votes requires at least 1 usable reference")
        return max(1, min(configured_min_votes, usable_reference_count))


@dataclass
class AnprConfig:
    # Skip plate localization/OCR on vehicle crops smaller than this - too
    # small to contain a legible plate no matter how much it's upscaled.
    min_vehicle_width: int = 100
    min_vehicle_height: int = 80

    # Run plate localization + OCR on active vehicle tracks every N frames
    # (the expensive step - periodic sampling, same idea as PersonIDConfig's
    # face_sample_stride).
    ocr_sample_stride: int = 5
    # Cap on stored OCR observations per track (bounds memory/compute; old
    # observations are dropped once the cap is hit).
    max_observations_per_track: int = 20
    # A track's leading (exact-text) OCR reading needs at least this many
    # agreeing observations, AND a mean OCR confidence >= confirm_min_mean_confidence
    # (0-100 scale, Tesseract's convention), before it's promoted from a
    # provisional "read" to a "confirmed" plate.
    vote_min_observations: int = 3
    confirm_min_mean_confidence: float = 55.0
    # OCR reads below this confidence aren't even considered as observations -
    # pure noise floor cut before aggregation ever sees them.
    min_read_confidence: float = 25.0

    # Plate search (Mode 2): normalized-string similarity threshold and max
    # length difference tolerated when comparing an OCR read against the
    # user's requested plate. Deliberately conservative - see
    # modules.anpr.ocr.plates_match for why.
    search_match_threshold: float = 0.85
    search_match_max_len_diff: int = 2
    # A single matching OCR read isn't enough to lock the red target box onto
    # a vehicle - require this many independently-matching frame observations
    # (mirrors PersonIDConfig.confirmation_observations).
    search_confirmation_observations: int = 2
    # Tolerate this many consecutive frames without the target vehicle's
    # track before treating it as lost (occlusion/temporary detection gap).
    gap_tolerance_frames: int = 45


@dataclass
class ZoneConfig:
    # Consecutive matching observations required before committing a state
    # transition - absorbs boundary jitter (entry) and brief false-outside
    # blips (exit) without spamming events.
    entry_grace_frames: int = 3
    exit_grace_frames: int = 15
    # Consecutive frames a previously-INSIDE track may go undetected
    # (occlusion/tracker gap) before it's treated as a real exit.
    track_absence_grace_frames: int = 45
    dwell_threshold_sec: float = 15.0
    # "footpoint" (bbox bottom-center, approximates ground contact) or
    # "centroid" (bbox center) - which point is tested against the zone.
    point_mode: str = "footpoint"
    # How long an ENTRY/EXIT/LONG_DWELL banner stays on screen, in seconds.
    banner_display_sec: float = 2.0


@dataclass
class BehaviorConfig:
    """All spatial thresholds are in PIXELS of the video's own processing
    resolution - they are therefore resolution-dependent by nature (a 60px
    loiter radius means something different on a 320-wide crop than a
    1920-wide frame). Defaults are tuned for the ~960px-wide clips used in
    this project's smoke tests; a deployment processing very different
    resolutions should override these.

    Timing uses SOURCE VIDEO timestamps (frame.timestamp_sec) throughout,
    never wall-clock processing time, so results don't depend on how fast
    the machine happens to process frames.
    """
    loitering_seconds: float = 10.0
    loitering_radius_px: float = 60.0

    direction_change_degrees: float = 70.0  # within the requested 60-90 range
    reversal_angle_degrees: float = 120.0  # a "reversal" is a near-opposite turn, not just any sharp turn

    speed_threshold_px_per_sec: float = 400.0
    acceleration_threshold_px_per_sec: float = 500.0  # |delta speed| between consecutive segments

    reversal_count: int = 3
    reversal_window_sec: float = 20.0
    reversal_radius_px: float = 90.0

    behavior_cooldown_seconds: float = 8.0

    # A movement "segment" (used for direction/speed) is only computed once
    # displacement since the last checkpoint clears this floor - filters
    # per-frame detector/tracker jitter from being read as real movement.
    min_displacement_px: float = 8.0
    # Minimum spacing between segment checkpoints; if displacement stays
    # below min_displacement_px the checkpoint simply doesn't advance yet
    # (so the next check spans a longer, less noisy baseline).
    sample_interval_sec: float = 0.3

    # How long a behavior alert stays visually active on the output video.
    alert_display_sec: float = 2.0


@dataclass
class LowLightConfig:
    """Automatic low-light detection + enhancement.

    Detection runs on a downsampled copy of every frame (cheap: a resize
    plus a LAB conversion and two numpy reductions) and only frames
    classified LOW_LIGHT ever reach the enhancement path - bright footage is
    never touched. All thresholds are on OpenCV's 8-bit LAB L channel
    (0-255), so they carry over as-is regardless of processing resolution.
    """
    enabled: bool = True
    backend: str = "fast"  # "fast" (CLAHE + adaptive gamma) | "zero_dce" (optional, see core/lowlight.py)

    # A frame is LOW_LIGHT if its mean L is below this OR its 10th-percentile
    # L (catches large dark regions/shadows even when the overall mean looks
    # moderate) is below shadow_p10_threshold.
    mean_threshold: float = 65.0
    shadow_p10_threshold: float = 25.0
    # Brightness analysis is done on a frame resized so its longer side is
    # at most this many pixels - negligible cost regardless of source
    # resolution.
    sample_max_dim: int = 320

    clahe_clip_limit: float = 2.5
    clahe_tile_size: int = 8
    # Adaptive gamma brightens further only if CLAHE alone left the frame
    # below this target L mean; gamma is solved for algebraically, then
    # clamped to gamma_min so it can never over-brighten into a washed-out,
    # noisy result.
    gamma_target_mean: float = 130.0
    gamma_min: float = 0.4


@dataclass
class AppConfig:
    video: VideoEngineConfig = field(default_factory=VideoEngineConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    person_id: PersonIDConfig = field(default_factory=PersonIDConfig)
    anpr: AnprConfig = field(default_factory=AnprConfig)
    zone: ZoneConfig = field(default_factory=ZoneConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    lowlight: LowLightConfig = field(default_factory=LowLightConfig)


def get_config() -> AppConfig:
    return AppConfig()
