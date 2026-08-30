"""Tests for PersonReID's pure logic (preprocessing shape, cosine similarity,
batch padding/slicing) without loading the real ONNX model -- a fake session
stands in so these stay fast unit tests."""
import numpy as np

from backend.modules.person_id.person_reid import PersonReID, _preprocess


class _FakeSession:
    """Returns a distinct, deterministic embedding per batch row so padding/
    slicing bugs (wrong row picked, wrong count returned) are detectable."""

    def get_inputs(self):
        class _Inp:
            name = "input"

        return [_Inp()]

    def run(self, _output_names, feed):
        batch = feed["input"]
        n = batch.shape[0]
        # embedding = a distinct one-hot-ish vector derived from each row's mean,
        # so two identical input rows (from batch padding) produce identical output
        return [np.stack([np.full(512, float(i) + batch[i].mean(), dtype=np.float32) for i in range(n)])]


def _make_reid() -> PersonReID:
    reid = PersonReID.__new__(PersonReID)  # bypass __init__ -- no real model load
    reid._session = _FakeSession()
    reid._input_name = "input"
    return reid


def test_preprocess_shape_and_dtype():
    crop = np.full((80, 40, 3), 128, dtype=np.uint8)
    out = _preprocess(crop)
    assert out.shape == (3, 256, 128)  # CHW, model's expected 256x128
    assert out.dtype == np.float32


def test_similarity_is_cosine_dot_product():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert PersonReID.similarity(a, b) == 1.0
    assert PersonReID.similarity(a, c) == 0.0


def test_embed_batch_preserves_order_and_count():
    reid = _make_reid()
    crops = [np.full((80, 40, 3), v, dtype=np.uint8) for v in (10, 50, 200)]
    results = reid.embed_batch(crops)
    assert len(results) == 3
    assert all(r is not None for r in results)
    # all embeddings should be L2-normalized
    for r in results:
        assert abs(np.linalg.norm(r) - 1.0) < 1e-5


def test_embed_batch_handles_more_than_fixed_batch_size():
    reid = _make_reid()
    crops = [np.full((80, 40, 3), v % 255, dtype=np.uint8) for v in range(20)]  # > batch size of 16
    results = reid.embed_batch(crops)
    assert len(results) == 20
    assert all(r is not None for r in results)


def test_embed_batch_skips_none_and_empty_crops():
    reid = _make_reid()
    crops = [np.full((80, 40, 3), 100, dtype=np.uint8), None, np.zeros((0, 0, 3), dtype=np.uint8)]
    results = reid.embed_batch(crops)
    assert len(results) == 3
    assert results[0] is not None
    assert results[1] is None
    assert results[2] is None


def test_embed_batch_empty_input():
    reid = _make_reid()
    assert reid.embed_batch([]) == []
