"""Bounded appearance gallery for one locked target.

Stores ReID embeddings collected while confidently associated with the
target, and reports how well a new probe embedding matches the gallery
overall. Deliberately does NOT decide gating itself -- the caller (pipeline)
only calls add() when its own conditions hold (good bbox size AND (face
confirms OR very-high ReID similarity)) -- see section 6/12 of the plan.
This is what prevents identity drift: a single uncertain observation can
never corrupt the gallery, because it's never added in the first place.
"""
from __future__ import annotations

from collections import deque

import numpy as np


class TargetGallery:
    def __init__(self, max_size: int = 30):
        self.max_size = max_size
        self._embeddings: deque[np.ndarray] = deque(maxlen=max_size)

    def add(self, embedding: np.ndarray) -> None:
        self._embeddings.append(embedding)

    def __len__(self) -> int:
        return len(self._embeddings)

    def best_similarity(self, probe: np.ndarray) -> float:
        """Max cosine similarity between probe and any stored embedding, or
        -1.0 if the gallery is empty (never a false match)."""
        if not self._embeddings:
            return -1.0
        return max(float(np.dot(probe, e)) for e in self._embeddings)
