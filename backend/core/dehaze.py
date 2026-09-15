"""Automatic haze/mist detection + CPU-friendly dehazing (Dark Channel Prior).

Shared core capability (like video.py/tracker.py/lowlight.py) so any
pipeline can opt into it: analyze_haze() is cheap enough to run on every
frame (small working resolution + a local min-filter), and dehaze_frame()
only ever touches frames analyze_haze() classified HAZY - clear footage is
never processed.

Method: Dark Channel Prior (He, Sun, Tang, "Single Image Haze Removal Using
Dark Channel Prior", CVPR 2009). For haze-free outdoor images, the "dark
channel" (per-pixel min over color channels, then a local min filter) is
close to zero almost everywhere - some channel in most local patches has a
dark pixel (shadow, colorful surface, dark object). Atmospheric haze/mist
adds scattered "airlight" that raises this floor everywhere, in proportion
to haze density. That same elevated dark channel doubles as both the haze
SIGNAL (its mean classifies HAZY vs CLEAR) and the basis for the
transmission map used to invert the haze model and recover the underlying
scene - one CPU-cheap computation serves both jobs, mirroring lowlight.py's
brightness-stats-for-both-classify-and-enhance shape.

No learned model - deliberately, same reasoning as lowlight.py's zero_dce
note: fetching/pinning an unverified dehazing network's weights without
testing them against this environment is out of scope, and Dark Channel
Prior is a well-established classical technique that needs no training
data and runs entirely on CPU.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from backend.config import DehazeConfig

CLEAR, HAZY = "CLEAR", "HAZY"


@dataclass
class HazeStats:
    dark_channel_mean: float
    classification: str


@dataclass
class DehazeInfo:
    classification: str
    enhanced: bool
    dark_channel_mean_before: float
    transmission_mean: float | None = None


def _dark_channel(image_f: np.ndarray, patch: int) -> np.ndarray:
    """Per-pixel min over BGR channels, then a local min filter (erosion)
    over a `patch`x`patch` window - the Dark Channel Prior's core primitive.
    `image_f` is float, any range (0-1 for the real image, or already-
    normalized for the atmospheric-light-divided image used in transmission
    estimation)."""
    min_channel = np.min(image_f, axis=2)
    patch = max(1, patch | 1)  # odd size, so the window is centered
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (patch, patch))
    return cv2.erode(min_channel, kernel)


def analyze_haze(image: np.ndarray | None, config: DehazeConfig) -> HazeStats:
    """Cheap haze classification: resize to a small working size, compute
    the dark channel, take its mean. Safe on None/empty input (classified
    CLEAR - nothing to dehaze)."""
    if image is None or image.size == 0:
        return HazeStats(0.0, CLEAR)

    h, w = image.shape[:2]
    longer = max(h, w)
    scale = min(1.0, config.sample_max_dim / longer) if longer > 0 else 1.0
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1.0 else image

    image_f = small.astype(np.float32) / 255.0
    dark = _dark_channel(image_f, config.dark_channel_patch)
    mean_dc = float(dark.mean())
    classification = HAZY if mean_dc >= config.haze_dark_channel_threshold else CLEAR
    return HazeStats(mean_dc, classification)


def _estimate_atmospheric_light(image_f: np.ndarray, dark: np.ndarray, top_frac: float) -> np.ndarray:
    """Standard DCP heuristic: among the pixels with the highest dark-
    channel value (the most haze-opaque patches - typically sky/distant
    haze glow), pick the one with the brightest original pixel as the
    atmospheric light estimate. Avoids latching onto a bright foreground
    object instead of the actual airlight color."""
    h, w = dark.shape
    n_pixels = max(1, int(h * w * top_frac))
    flat_dark = dark.reshape(-1)
    flat_img = image_f.reshape(-1, 3)
    idx = np.argpartition(flat_dark, -n_pixels)[-n_pixels:]
    brightest = idx[np.argmax(flat_img[idx].sum(axis=1))]
    return flat_img[brightest]


def _refine_transmission(gray: np.ndarray, transmission: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """Edge-preserving refinement so the transmission map doesn't leave hard
    per-patch block artifacts around object boundaries. Uses a true guided
    filter when available (cv2.ximgproc, from opencv-contrib); the pinned
    opencv-python (non-contrib) dependency in this project doesn't ship
    that module, so this falls back to a box-filtered mean - softer edge
    preservation, but still removes the hard blocking, at zero extra
    dependency cost."""
    ximgproc = getattr(cv2, "ximgproc", None)
    if ximgproc is not None and hasattr(ximgproc, "guidedFilter"):
        return ximgproc.guidedFilter(guide=gray.astype(np.float32), src=transmission.astype(np.float32), radius=radius, eps=eps)
    return cv2.boxFilter(transmission.astype(np.float32), -1, (radius, radius))


def dehaze_frame(image: np.ndarray, config: DehazeConfig) -> tuple[np.ndarray, HazeStats, float]:
    """Runs the actual Dark Channel Prior recovery - callers should only
    invoke this once analyze_haze() has already classified the frame HAZY
    (see process_frame). Returns (dehazed image, stats used, mean
    transmission)."""
    stats = analyze_haze(image, config)
    image_f = image.astype(np.float32) / 255.0
    dark = _dark_channel(image_f, config.dark_channel_patch)
    atmospheric_light = _estimate_atmospheric_light(image_f, dark, config.atmospheric_light_top_frac)

    normalized = image_f / np.maximum(atmospheric_light, 1e-3)
    transmission = 1.0 - config.omega * _dark_channel(normalized, config.dark_channel_patch)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    transmission_refined = _refine_transmission(gray, transmission, config.guided_filter_radius, config.guided_filter_eps)

    t = np.clip(transmission_refined, config.min_transmission, 1.0)[..., None]
    recovered = (image_f - atmospheric_light) / t + atmospheric_light
    recovered = np.clip(recovered, 0.0, 1.0)
    out = (recovered * 255.0).astype(np.uint8)

    return out, stats, float(transmission_refined.mean())


def process_frame(image: np.ndarray | None, config: DehazeConfig) -> tuple[np.ndarray, DehazeInfo]:
    """The single entry point pipelines should call: classify, and dehaze
    only if warranted. Returns (possibly-dehazed image, info). Never
    mutates the input array in place."""
    if image is None or image.size == 0:
        return image, DehazeInfo(CLEAR, False, 0.0)

    stats = analyze_haze(image, config)
    if not config.enabled or stats.classification == CLEAR:
        return image, DehazeInfo(stats.classification, False, stats.dark_channel_mean)

    out, _stats, transmission_mean = dehaze_frame(image, config)
    return out, DehazeInfo(
        classification=stats.classification, enhanced=True,
        dark_channel_mean_before=stats.dark_channel_mean, transmission_mean=transmission_mean,
    )
