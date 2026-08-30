"""Reference-photo handling tests using real YuNet+SFace models.

Uses the ground-truth fixtures under references/smoke_target (two photos of
the same person, cropped from different frames of the same real video) and
references/smoke_unrelated (a different person entirely) - see
scratchpad notes: these were built by detecting faces with YuNet in real
footage and cropping around them, so "same person" / "different person" is
known by construction, not assumed.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.config import PersonIDConfig, SFACE_MODEL_PATH, YUNET_MODEL_PATH
from backend.modules.person_id.detector import FaceDetector
from backend.modules.person_id.recognizer import FaceRecognizer, ReferenceSet

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET_REF1 = REPO_ROOT / "references" / "smoke_target" / "ref1.jpg"
TARGET_REF2 = REPO_ROOT / "references" / "smoke_target" / "ref2.jpg"
UNRELATED_REF1 = REPO_ROOT / "references" / "smoke_unrelated" / "ref1.jpg"

pytestmark = pytest.mark.skipif(
    not (TARGET_REF1.exists() and TARGET_REF2.exists() and UNRELATED_REF1.exists()),
    reason="ground-truth reference fixtures not present",
)


@pytest.fixture(scope="module")
def detector():
    return FaceDetector(YUNET_MODEL_PATH)


@pytest.fixture(scope="module")
def recognizer():
    return FaceRecognizer(SFACE_MODEL_PATH)


def test_single_reference_photo_is_usable(detector, recognizer):
    refset = ReferenceSet([TARGET_REF1], detector, recognizer)
    assert refset.usable_count == 1
    assert refset.rejected == []
    votes = PersonIDConfig.resolve_votes(configured_min_votes=2, usable_reference_count=refset.usable_count)
    assert votes == 1  # must not demand 2 votes from 1 reference


def test_multiple_reference_photos_all_usable(detector, recognizer):
    refset = ReferenceSet([TARGET_REF1, TARGET_REF2], detector, recognizer)
    assert refset.usable_count == 2
    votes = PersonIDConfig.resolve_votes(configured_min_votes=2, usable_reference_count=refset.usable_count)
    assert votes == 2


def test_unreadable_or_faceless_photo_is_rejected_not_crashed(tmp_path, detector, recognizer):
    blank_path = tmp_path / "blank.jpg"
    cv2.imwrite(str(blank_path), np.full((200, 200, 3), 128, dtype=np.uint8))

    refset = ReferenceSet([TARGET_REF1, blank_path], detector, recognizer)
    assert refset.usable_count == 1  # blank image dropped, not fatal
    assert len(refset.rejected) == 1
    assert refset.rejected[0][0] == blank_path


def test_same_person_scores_above_threshold_different_person_does_not(detector, recognizer):
    cfg = PersonIDConfig()
    refset = ReferenceSet([TARGET_REF1], detector, recognizer)

    probe_same = cv2.imread(str(TARGET_REF2))
    face_same = detector.best(probe_same)
    emb_same = recognizer.embed(probe_same, face_same)
    votes_same, sim_same = refset.vote(emb_same, cfg.similarity_threshold)
    assert votes_same >= 1
    assert sim_same >= cfg.similarity_threshold

    probe_diff = cv2.imread(str(UNRELATED_REF1))
    face_diff = detector.best(probe_diff)
    emb_diff = recognizer.embed(probe_diff, face_diff)
    votes_diff, sim_diff = refset.vote(emb_diff, cfg.similarity_threshold)
    assert votes_diff == 0
    assert sim_diff < cfg.similarity_threshold
