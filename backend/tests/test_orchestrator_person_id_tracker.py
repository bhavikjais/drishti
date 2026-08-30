"""Proves the COMBINED job path (CombinedPipeline / backend/orchestrator.py)
actually uses the new BoT-SORT+OSNet PersonBotSortTracker for person_id, not
the old shared ByteTrack-only ObjectTracker -- the specific requirement of
this integration pass. A spy on PersonBotSortTracker.update is the most
direct possible proof: if this fails, the combined job silently reverted to
(or never left) the old tracking path.
"""
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from backend.config import REPO_ROOT
from backend.modules.person_id.custom_tracker import PersonBotSortTracker
from backend.orchestrator import CombinedPipeline, OrchestratorRequest

REF_PHOTO = REPO_ROOT / "references" / "smoke_target" / "ref1.jpg"


def _make_synthetic_video(path, n_frames=12, fps=10.0, size=(160, 120)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    rng = np.random.default_rng(0)
    for _ in range(n_frames):
        writer.write(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
    writer.release()


def test_combined_person_id_uses_new_tracker(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video_path)
    output_path = tmp_path / "out.mp4"

    real_update = PersonBotSortTracker.update
    with patch.object(PersonBotSortTracker, "update", autospec=True) as spy:
        spy.side_effect = lambda self, frame: real_update(self, frame)
        req = OrchestratorRequest(enable_person_id=True, reference_photo_paths=[REF_PHOTO])
        CombinedPipeline(req).run(video_path, output_path)

    assert spy.called, "CombinedPipeline did not call PersonBotSortTracker.update -- the combined job path is not using the new tracker"
    assert spy.call_count >= 1


def test_combined_person_id_plus_anpr_still_uses_new_tracker_for_person(tmp_path):
    """The case this integration was specifically about: person_id combined
    with another module (anpr) in one job must still use the new tracker for
    the person target, alongside the shared tracker still serving anpr."""
    video_path = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video_path)
    output_path = tmp_path / "out.mp4"

    real_update = PersonBotSortTracker.update
    with patch.object(PersonBotSortTracker, "update", autospec=True) as spy:
        spy.side_effect = lambda self, frame: real_update(self, frame)
        req = OrchestratorRequest(enable_person_id=True, reference_photo_paths=[REF_PHOTO], enable_anpr=True)
        result = CombinedPipeline(req).run(video_path, output_path)

    assert spy.called
    assert result.anpr is not None  # anpr still ran via the shared tracker, unaffected
    assert result.person_id is not None
