"""Orchestrator combination-matrix tests.

These run the REAL CombinedPipeline (real YOLO tracker, real video I/O) on
a tiny synthetic clip for every module combination in the task's matrix -
proving each combination wires up and runs to completion without crashing,
produces a complete/playable output video, and (via a single grep-verified
call site) only ever creates one ObjectTracker per run regardless of how
many modules are enabled.

Genuine detection accuracy (a real confirmed target, a real plate, real
zone crossings) is verified separately by the real-video end-to-end test
(test_api.py's combined-job test / scripts), same split as every other
module: synthetic here for plumbing, real footage there for behavior.
"""
import re
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.config import REPO_ROOT
from backend.orchestrator import CombinedPipeline, OrchestratorError, OrchestratorRequest
from backend.modules.zone.geometry import Zone

REF_PHOTO = REPO_ROOT / "references" / "smoke_target" / "ref1.jpg"


def _make_synthetic_video(path, n_frames=8, fps=10.0, size=(160, 120)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    rng = np.random.default_rng(0)
    for _ in range(n_frames):
        writer.write(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
    writer.release()


def test_orchestrator_source_has_exactly_one_tracker_instantiation():
    # structural guarantee, independent of which modules are enabled -
    # the combination matrix below exercises this at runtime.
    src = Path(__file__).resolve().parent.parent / "orchestrator.py"
    text = src.read_text()
    assert len(re.findall(r"ObjectTracker\(", text)) == 1


@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory):
    path = tmp_path_factory.mktemp("orch") / "synthetic.mp4"
    _make_synthetic_video(path)
    return path


def _zone():
    return Zone(zone_id="oz1", video_id="v1", label="Zone", shape="rectangle", points=[(0.1, 0.1), (0.9, 0.9)])


COMBINATIONS = {
    "A_person_only": dict(enable_person_id=True, reference_photo_paths=[REF_PHOTO]),
    "B_anpr_only": dict(enable_anpr=True),
    "C_zone_only": dict(zones=[_zone()]),
    "D_behavior_only": dict(enable_behavior=True),
    "E_lowlight_only": dict(enable_lowlight=True),
    "F_person_anpr": dict(enable_person_id=True, reference_photo_paths=[REF_PHOTO], enable_anpr=True),
    "G_person_zone": dict(enable_person_id=True, reference_photo_paths=[REF_PHOTO], zones=[_zone()]),
    "H_person_behavior": dict(enable_person_id=True, reference_photo_paths=[REF_PHOTO], enable_behavior=True),
    "I_person_lowlight": dict(enable_person_id=True, reference_photo_paths=[REF_PHOTO], enable_lowlight=True),
    "J_anpr_zone": dict(enable_anpr=True, zones=[_zone()]),
    "K_anpr_behavior": dict(enable_anpr=True, enable_behavior=True),
    "L_anpr_lowlight": dict(enable_anpr=True, enable_lowlight=True),
    "M_zone_behavior": dict(zones=[_zone()], enable_behavior=True),
    "N_zone_lowlight": dict(zones=[_zone()], enable_lowlight=True),
    "O_behavior_lowlight": dict(enable_behavior=True, enable_lowlight=True),
    "P_everything": dict(enable_person_id=True, reference_photo_paths=[REF_PHOTO], enable_anpr=True, zones=[_zone()], enable_behavior=True, enable_lowlight=True),
}


@pytest.mark.parametrize("combo_name", list(COMBINATIONS.keys()))
def test_combination_runs_and_produces_complete_output(combo_name, synthetic_video, tmp_path):
    kwargs = COMBINATIONS[combo_name]
    req = OrchestratorRequest(**kwargs)
    output_path = tmp_path / f"{combo_name}.mp4"

    result = CombinedPipeline(req).run(synthetic_video, output_path)

    assert result.video_info.frame_count == 8
    assert result.metrics["frames_read"] == 8
    assert result.metrics["frames_written"] == 8
    assert result.browser_playable in (True, False)  # must be reported either way
    assert isinstance(result.events, list)

    cap = cv2.VideoCapture(str(output_path))
    assert cap.isOpened()
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 8
    cap.release()

    if kwargs.get("enable_person_id"):
        assert result.person_id is not None
    if kwargs.get("enable_anpr"):
        assert result.anpr is not None
    if kwargs.get("zones"):
        assert result.zones is not None and len(result.zones) == len(kwargs["zones"])
    if kwargs.get("enable_behavior"):
        assert result.behavior is not None
    if kwargs.get("enable_lowlight"):
        assert result.lowlight is not None


def test_no_modules_enabled_raises_clear_error(synthetic_video, tmp_path):
    with pytest.raises(OrchestratorError):
        CombinedPipeline(OrchestratorRequest()).run(synthetic_video, tmp_path / "x.mp4")


def test_person_id_without_references_raises_clear_error(synthetic_video, tmp_path):
    with pytest.raises(OrchestratorError):
        CombinedPipeline(OrchestratorRequest(enable_person_id=True)).run(synthetic_video, tmp_path / "x.mp4")


def test_cancellation_mid_run_still_closes_writer_cleanly(tmp_path):
    # a larger clip so cancellation actually lands mid-processing, not on the last frame
    video_path = tmp_path / "longer.mp4"
    _make_synthetic_video(video_path, n_frames=40, fps=10.0, size=(160, 120))
    output_path = tmp_path / "cancelled.mp4"

    class _Cancel(Exception):
        pass

    seen = []

    def progress_cb(p):
        seen.append(p)
        if len(seen) >= 3:
            raise _Cancel("simulated cancellation")

    req = OrchestratorRequest(zones=[_zone()])
    with pytest.raises(_Cancel):
        CombinedPipeline(req).run(video_path, output_path, progress_cb=progress_cb)

    # writer.close() must still have run (finally block) - the partial file
    # should be a valid, openable video, not a corrupted/locked handle.
    assert output_path.exists()
    cap = cv2.VideoCapture(str(output_path))
    assert cap.isOpened()
    written_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    assert 0 < written_frames < 40  # genuinely stopped partway, not the full clip


def test_multiple_zones_each_get_independent_summary(synthetic_video, tmp_path):
    zone_a = Zone(zone_id="za", video_id="v1", label="Zone A", shape="rectangle", points=[(0.0, 0.0), (0.5, 0.5)])
    zone_b = Zone(zone_id="zb", video_id="v1", label="Zone B", shape="rectangle", points=[(0.5, 0.5), (1.0, 1.0)])
    req = OrchestratorRequest(zones=[zone_a, zone_b])
    result = CombinedPipeline(req).run(synthetic_video, tmp_path / "multi_zone.mp4")
    assert [z["zone_id"] for z in result.zones] == ["za", "zb"]
