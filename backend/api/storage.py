"""File-backed storage for uploaded videos and zone definitions.

No database for this phase - videos live under uploads/{video_id}{ext},
zones are one JSON file per zone under zones/{zone_id}.json. Simple, and
matches the top-level uploads/ / zones/ directories the project already
uses for on-disk state.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from backend.config import REFERENCES_DIR, UPLOADS_DIR, ZONES_DIR
from backend.modules.zone.geometry import Zone


class NotFoundError(Exception):
    pass


def new_id() -> str:
    return uuid.uuid4().hex


def save_uploaded_video(filename: str, data: bytes) -> tuple[str, Path]:
    video_id = new_id()
    ext = Path(filename).suffix or ".mp4"
    path = UPLOADS_DIR / f"{video_id}{ext}"
    path.write_bytes(data)
    return video_id, path


def find_video_path(video_id: str) -> Path:
    matches = list(UPLOADS_DIR.glob(f"{video_id}.*"))
    if not matches:
        raise NotFoundError(f"video not found: {video_id}")
    return matches[0]


def save_zone(zone: Zone) -> None:
    path = ZONES_DIR / f"{zone.zone_id}.json"
    path.write_text(json.dumps(zone.to_dict(), indent=2))


def load_zone(zone_id: str) -> Zone:
    path = ZONES_DIR / f"{zone_id}.json"
    if not path.is_file():
        raise NotFoundError(f"zone not found: {zone_id}")
    return Zone.from_dict(json.loads(path.read_text()))


def save_reference_photos(files: list[tuple[str, bytes]]) -> tuple[str, list[Path]]:
    """Saves 1-6 uploaded reference photos under references/{reference_set_id}/
    and returns (reference_set_id, [paths]). Validation of the 1-6 count and
    of "does at least one contain a usable face" is the pipeline's job
    (ReferenceSet already handles per-photo rejection without crashing) -
    this layer just persists bytes to disk."""
    ref_id = new_id()
    ref_dir = REFERENCES_DIR / ref_id
    ref_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (filename, data) in enumerate(files):
        ext = Path(filename).suffix or ".jpg"
        path = ref_dir / f"{i}{ext}"
        path.write_bytes(data)
        paths.append(path)
    return ref_id, paths


def find_reference_photos(reference_set_id: str) -> list[Path]:
    ref_dir = REFERENCES_DIR / reference_set_id
    if not ref_dir.is_dir():
        raise NotFoundError(f"reference set not found: {reference_set_id}")
    return sorted(ref_dir.glob("*"))
