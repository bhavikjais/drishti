"""YuNet face detection wrapper (cv2.FaceDetectorYN)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class FaceDetection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in the coordinate space of the image passed in
    confidence: float
    raw: np.ndarray  # full YuNet row (bbox + 5 landmarks + score), needed by SFace alignCrop


class FaceDetector:
    def __init__(self, model_path: str | Path, score_threshold: float = 0.7):
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"YuNet model not found: {self.model_path}")
        self._detector = cv2.FaceDetectorYN.create(
            str(self.model_path), "", (320, 320),
            score_threshold=score_threshold, nms_threshold=0.3, top_k=50,
        )

    _MIN_INPUT_SIDE = 16  # YuNet produces garbage (incl. inf) on tiny crops

    def detect(self, image: np.ndarray) -> list[FaceDetection]:
        if image is None or image.size == 0:
            return []
        h, w = image.shape[:2]
        if h < self._MIN_INPUT_SIDE or w < self._MIN_INPUT_SIDE:
            return []
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(image)
        if faces is None:
            return []
        out = []
        for row in faces:
            if not np.all(np.isfinite(row)):
                continue
            x, y, bw, bh = row[0:4]
            x1, y1 = max(0, int(x)), max(0, int(y))
            x2, y2 = min(w, int(x + bw)), min(h, int(y + bh))
            if x2 <= x1 or y2 <= y1:
                continue
            out.append(FaceDetection(bbox=(x1, y1, x2, y2), confidence=float(row[-1]), raw=row))
        out.sort(key=lambda f: f.confidence, reverse=True)
        return out

    def best(self, image: np.ndarray) -> FaceDetection | None:
        faces = self.detect(image)
        return faces[0] if faces else None
