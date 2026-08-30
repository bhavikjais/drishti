"""Person re-identification via OSNet x0_25 (MSMT17-trained, ONNX).

This answers a narrower question than face recognition: "does this detected
person LOOK like the target we were already tracking?" -- not "who is this,
globally". It's what keeps the target's identity attached to their body when
the face is turned away, occluded, or too small to read -- face recognition
alone cannot do this (that's exactly why this rebuild exists).

Model: anriha/osnet_x0_25_msmt17 (HuggingFace, MIT license) -- verified by
downloading and running it directly before adopting it: input [16,3,256,128]
(fixed batch of 16), output [16,512], ~2.5ms/crop on CPU. Empirically
validated preprocessing (standard ImageNet mean/std normalization, the
convention this whole model family -- torchreid/OSNet -- was trained with) on
real footage: same-person cosine similarity 0.876 vs different-person 0.42-0.53
-- a wide, usable margin. No new pip dependency: runs on onnxruntime, already
installed for ANPR.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

_INPUT_HEIGHT = 256
_INPUT_WIDTH = 128
_BATCH_SIZE = 16  # the exported model has a fixed batch dimension
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _preprocess(crop: np.ndarray) -> np.ndarray:
    """BGR crop -> normalized CHW float32, resized to the model's expected 256x128."""
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (_INPUT_WIDTH, _INPUT_HEIGHT), interpolation=cv2.INTER_LINEAR)
    arr = resized.astype(np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    return arr.transpose(2, 0, 1)  # HWC -> CHW


class PersonReID:
    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"OSNet ReID model not found: {self.model_path}")
        # Pin to CPU -- onnxruntime on Windows auto-registers AzureExecutionProvider
        # alongside CPU, which is both a hidden network dependency (must stay
        # offline) and, measured elsewhere in this project, ~8-10x slower per call.
        self._session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

    def embed_batch(self, crops: list[np.ndarray]) -> list[np.ndarray | None]:
        """Returns one L2-normalized 512-d embedding per crop (None for a crop too
        degenerate to process), preserving input order. Crops are batched together
        (padded to the model's fixed batch=16 with repeats of the last real crop,
        then sliced back) so multiple tracks sampled the same frame cost one
        inference call, not one per track."""
        if not crops:
            return []
        valid_idx = [i for i, c in enumerate(crops) if c is not None and c.size > 0]
        if not valid_idx:
            return [None] * len(crops)

        results: list[np.ndarray | None] = [None] * len(crops)
        for start in range(0, len(valid_idx), _BATCH_SIZE):
            chunk = valid_idx[start : start + _BATCH_SIZE]
            batch = np.stack([_preprocess(crops[i]) for i in chunk])
            if len(chunk) < _BATCH_SIZE:
                pad = np.repeat(batch[-1:], _BATCH_SIZE - len(chunk), axis=0)
                batch = np.concatenate([batch, pad], axis=0)
            out = self._session.run(None, {self._input_name: batch})[0]
            for j, i in enumerate(chunk):
                vec = out[j]
                norm = np.linalg.norm(vec)
                results[i] = (vec / norm) if norm > 0 else None
        return results

    def embed(self, crop: np.ndarray) -> np.ndarray | None:
        return self.embed_batch([crop])[0]

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity -- both inputs are already L2-normalized by embed(),
        so this is just a dot product."""
        return float(np.dot(a, b))
