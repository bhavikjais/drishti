"""Annotated output-video writing with H.264-first codec fallback.

cv2.VideoWriter's codec support is build-dependent: a plain pip opencv-python
wheel usually lacks a bundled H.264 encoder, so we try a small list of
browser-friendly fourccs in order and report whichever one actually accepted
frames. If none of them work we fall back to mp4v (always available in
opencv-python) and say so explicitly rather than silently producing a
non-browser-playable file.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.core.video import VideoInfo

logger = logging.getLogger(__name__)

# Colors are BGR (OpenCV convention).
RED = (0, 0, 255)
YELLOW = (0, 220, 255)
CYAN = (255, 220, 0)
GREEN = (60, 200, 60)
ORANGE = (0, 140, 255)
MAGENTA = (200, 0, 200)
WHITE = (255, 255, 255)


def format_timestamp(seconds: float) -> str:
    """0.0 -> '00:00.0', 14.2 -> '00:14.2', 75.3 -> '01:15.3'."""
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:04.1f}"


class OutputVideoWriteError(RuntimeError):
    pass


@dataclass
class OpenResult:
    codec_used: str
    browser_playable: bool


class OutputVideoWriter:
    """Wraps cv2.VideoWriter with codec fallback and frame-count bookkeeping."""

    # avc1/H264 = H.264 (browser-playable via MP4). mp4v is a last-resort
    # fallback that many browsers will NOT play inline.
    _BROWSER_PLAYABLE = {"avc1", "H264", "X264"}

    def __init__(
        self,
        path: str | Path,
        info: VideoInfo,
        codec_candidates: tuple[str, ...] = ("avc1", "H264", "mp4v"),
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.info = info
        self._writer: cv2.VideoWriter | None = None
        self.frames_written = 0
        self.open_result = self._open(codec_candidates)

    def _open(self, codec_candidates: tuple[str, ...]) -> OpenResult:
        last_err = None
        for codec in codec_candidates:
            try:
                fourcc = cv2.VideoWriter_fourcc(*codec)
                writer = cv2.VideoWriter(
                    str(self.path),
                    fourcc,
                    self.info.fps,
                    (self.info.width, self.info.height),
                )
                if writer.isOpened():
                    self._writer = writer
                    playable = codec in self._BROWSER_PLAYABLE
                    if not playable:
                        logger.warning(
                            "Output codec fallback: %s is not reliably "
                            "browser-playable (tried %s first). File: %s",
                            codec,
                            codec_candidates,
                            self.path,
                        )
                    return OpenResult(codec_used=codec, browser_playable=playable)
                writer.release()
            except Exception as exc:  # pragma: no cover - codec probing
                last_err = exc
                continue
        raise OutputVideoWriteError(
            f"No usable video codec found among {codec_candidates} "
            f"for output {self.path} (last error: {last_err})"
        )

    def write(self, image: np.ndarray) -> None:
        if self._writer is None:
            raise OutputVideoWriteError("writer is closed")
        if image.shape[1] != self.info.width or image.shape[0] != self.info.height:
            image = cv2.resize(image, (self.info.width, self.info.height))
        self._writer.write(image)
        self.frames_written += 1

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None

    def __enter__(self) -> "OutputVideoWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def draw_target_box(
    image: np.ndarray,
    bbox: tuple[int, int, int, int],
    label: str | list[str] = "TARGET",
    color: tuple[int, int, int] = RED,
    thickness: int = 3,
) -> None:
    """Draws the single red target box (or any labeled box) in place.

    label may be a single string or a list of lines (e.g.
    ["TARGET VEHICLE", "DL01AB1234", "92%"]), stacked above the box.
    """
    x1, y1, x2, y2 = (int(v) for v in bbox)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    lines = [label] if isinstance(label, str) else [l for l in label if l]
    if not lines:
        return

    font, scale, weight = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
    sizes = [cv2.getTextSize(line, font, scale, weight)[0] for line in lines]
    line_h = max(h for _, h in sizes) + 10
    max_w = max(w for w, _ in sizes)
    top = max(0, y1 - line_h * len(lines))
    cv2.rectangle(image, (x1, top), (x1 + max_w + 6, top + line_h * len(lines)), color, -1)
    for i, line in enumerate(lines):
        baseline_y = top + line_h * (i + 1) - 6
        cv2.putText(image, line, (x1 + 3, baseline_y), font, scale, WHITE, weight, cv2.LINE_AA)


def draw_polygon(image: np.ndarray, points, color=YELLOW, thickness: int = 2, label: str | None = None) -> None:
    pts = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(image, [pts], isClosed=True, color=color, thickness=thickness)
    if label:
        x, y = min(p[0] for p in points), min(p[1] for p in points)
        font, scale, weight = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
        (tw, th), _ = cv2.getTextSize(label, font, scale, weight)
        box_h = th + 8
        # Prefer the label above the zone's top edge; if the zone touches the
        # frame edge there's no room above, so draw it just inside instead
        # (otherwise it clips off-screen).
        top = y - box_h if y - box_h >= 0 else y + 4
        cv2.rectangle(image, (int(x), int(top)), (int(x) + tw + 6, int(top) + box_h), color, -1)
        cv2.putText(image, label, (int(x) + 3, int(top) + box_h - 6), font, scale, (0, 0, 0), weight, cv2.LINE_AA)


def draw_predicted_path(
    image: np.ndarray,
    origin: tuple[float, float],
    target: tuple[float, float],
    color: tuple[int, int, int] = YELLOW,
    thickness: int = 2,
    dash_len: int = 10,
) -> None:
    """Dashed line + end marker from a track's current point to its
    extrapolated future position - visualizes a zone/forecast.py intent
    prediction (PREDICTED_ZONE_CROSSING) before the track actually gets
    there, so the operator sees WHY the alert fired, not just that it did.
    """
    ox, oy = origin
    tx, ty = target
    dist = ((tx - ox) ** 2 + (oy - ty) ** 2) ** 0.5
    if dist < 1e-3:
        return
    steps = max(1, int(dist // dash_len))
    for i in range(steps):
        if i % 2 == 1:
            continue  # skip alternate segments for the dashed look
        t0, t1 = i / steps, min(1.0, (i + 1) / steps)
        p0 = (int(ox + (tx - ox) * t0), int(oy + (ty - oy) * t0))
        p1 = (int(ox + (tx - ox) * t1), int(oy + (ty - oy) * t1))
        cv2.line(image, p0, p1, color, thickness)
    cv2.circle(image, (int(tx), int(ty)), 6, color, thickness)


def draw_banner(image: np.ndarray, lines: list[str], color: tuple[int, int, int], slot: int = 0) -> None:
    """Draws a stacked event banner (e.g. ["ZONE ENTRY", "PERSON #12",
    "00:14.2"]) anchored top-left. `slot` offsets multiple simultaneous
    banners vertically so they don't overlap.
    """
    font, scale, weight = cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2
    sizes = [cv2.getTextSize(line, font, scale, weight)[0] for line in lines]
    line_h = max(h for _, h in sizes) + 12
    max_w = max(w for w, _ in sizes) + 16
    top = 10 + slot * (line_h * len(lines) + 10)
    left = 10
    cv2.rectangle(image, (left, top), (left + max_w, top + line_h * len(lines)), color, -1)
    cv2.rectangle(image, (left, top), (left + max_w, top + line_h * len(lines)), WHITE, 2)
    for i, line in enumerate(lines):
        baseline_y = top + line_h * (i + 1) - 8
        cv2.putText(image, line, (left + 8, baseline_y), font, scale, WHITE, weight, cv2.LINE_AA)


def draw_hud_text(image: np.ndarray, lines: list[str], origin=(10, 24)) -> None:
    x, y = origin
    for i, line in enumerate(lines):
        yy = y + i * 22
        cv2.putText(image, line, (x, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, line, (x, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1, cv2.LINE_AA)
