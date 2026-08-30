"""SFace face recognition (cv2.FaceRecognizerSF) + multi-reference voting.

FaceRecognizerSF.match() returns cosine similarity in the recognizer's own
convention where higher = more similar; OpenCV's documented "same person"
cosine threshold for this model is ~0.363, but this project intentionally
uses a stricter 0.42 default (config.PersonIDConfig.similarity_threshold) to
cut false positives, combined with multi-reference voting.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.modules.person_id.detector import FaceDetection, FaceDetector

logger = logging.getLogger(__name__)


class FaceRecognizer:
    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"SFace model not found: {self.model_path}")
        self._recognizer = cv2.FaceRecognizerSF.create(str(self.model_path), "")

    def embed(self, image: np.ndarray, face: FaceDetection) -> np.ndarray:
        aligned = self._recognizer.alignCrop(image, face.raw)
        return self._recognizer.feature(aligned)

    def similarity(self, feat_a: np.ndarray, feat_b: np.ndarray) -> float:
        return float(self._recognizer.match(feat_a, feat_b, cv2.FaceRecognizerSF_FR_COSINE))


@dataclass
class ReferenceEmbedding:
    source_path: Path
    embedding: np.ndarray


class ReferenceSet:
    """Loads reference photos, detects+embeds the face in each, and drops
    unusable photos (no detectable face) rather than crashing.
    """

    def __init__(
        self,
        photo_paths: list[str | Path],
        detector: FaceDetector,
        recognizer: FaceRecognizer,
    ):
        self.detector = detector
        self.recognizer = recognizer
        self.embeddings: list[ReferenceEmbedding] = []
        self.rejected: list[tuple[Path, str]] = []

        for raw_path in photo_paths:
            path = Path(raw_path)
            image = cv2.imread(str(path))
            if image is None:
                self.rejected.append((path, "unreadable image file"))
                continue
            face = detector.best(image)
            if face is None:
                self.rejected.append((path, "no face detected"))
                continue
            embedding = recognizer.embed(image, face)
            self.embeddings.append(ReferenceEmbedding(source_path=path, embedding=embedding))

        if self.rejected:
            logger.warning("ReferenceSet: rejected %d/%d photos: %s",
                            len(self.rejected), len(photo_paths), self.rejected)

    @property
    def usable_count(self) -> int:
        return len(self.embeddings)

    def vote(self, probe_embedding: np.ndarray, threshold: float) -> tuple[int, float]:
        """Compares probe against every usable reference.

        Returns (vote_count, best_similarity) where vote_count is how many
        references matched at/above `threshold`.
        """
        votes = 0
        best = -1.0
        for ref in self.embeddings:
            sim = self.recognizer.similarity(probe_embedding, ref.embedding)
            best = max(best, sim)
            if sim >= threshold:
                votes += 1
        return votes, best
