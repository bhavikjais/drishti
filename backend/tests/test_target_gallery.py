import numpy as np

from backend.modules.person_id.target_gallery import TargetGallery


def _unit(vec):
    v = np.array(vec, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_empty_gallery_never_matches():
    gallery = TargetGallery(max_size=5)
    assert gallery.best_similarity(_unit([1, 0, 0])) == -1.0


def test_matches_added_embedding():
    gallery = TargetGallery(max_size=5)
    e = _unit([1, 0, 0])
    gallery.add(e)
    assert gallery.best_similarity(e) == 1.0


def test_best_similarity_is_max_over_gallery():
    gallery = TargetGallery(max_size=5)
    gallery.add(_unit([1, 0, 0]))
    gallery.add(_unit([0, 1, 0]))
    # probe close to the second entry, far from the first
    probe = _unit([0, 0.9, 0.1])
    sim = gallery.best_similarity(probe)
    assert sim > 0.9  # should match the close entry, not average with the far one


def test_bounded_size_evicts_oldest():
    gallery = TargetGallery(max_size=2)
    gallery.add(_unit([1, 0, 0]))
    gallery.add(_unit([0, 1, 0]))
    gallery.add(_unit([0, 0, 1]))  # evicts the first
    assert len(gallery) == 2
    # the first (evicted) entry should no longer perfectly match
    assert gallery.best_similarity(_unit([1, 0, 0])) < 1.0
