"""Per-track OCR observation aggregation.

A single frame's OCR read is never trusted on its own. Each track
accumulates a bounded window of (text, confidence) observations; the
aggregate is the exact normalized-text group with the highest total
confidence weight, distinguishing three states so the pipeline (and caller)
never has to guess:

  - no observations at all                    -> nothing to report
  - a leading candidate exists but hasn't      -> "read" (provisional,
    reached the observation-count/confidence      don't trust it yet)
    bar
  - the leading candidate cleared both bars    -> "confirmed"

Exact-text grouping (post-normalize_plate) is deliberate: a single garbage
frame just becomes its own singleton group and loses to a consistent
majority on any real, semi-legible plate - no fuzzy-matching is needed
internally, which keeps this deterministic and easy to test. Fuzzy matching
is reserved for the user search comparison (see ocr.plates_match), where the
noise being tolerated is "same physical plate, different frame", not
"aggregate arbitrary near-miss strings together".
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class PlateObservation:
    text: str
    confidence: float
    frame_index: int
    timestamp_sec: float


@dataclass
class AggregatedPlate:
    text: str
    mean_confidence: float
    observation_count: int
    total_observation_count: int  # across all text variants seen for this track
    confirmed: bool


class PlateAggregator:
    def __init__(self, max_observations_per_track: int, vote_min_observations: int, confirm_min_mean_confidence: float):
        self.max_observations_per_track = max_observations_per_track
        self.vote_min_observations = vote_min_observations
        self.confirm_min_mean_confidence = confirm_min_mean_confidence
        self._observations: dict[int, list[PlateObservation]] = defaultdict(list)

    def add_observation(self, track_id: int, text: str, confidence: float, frame_index: int, timestamp_sec: float) -> None:
        if not text:
            return
        obs_list = self._observations[track_id]
        obs_list.append(PlateObservation(text, confidence, frame_index, timestamp_sec))
        if len(obs_list) > self.max_observations_per_track:
            del obs_list[0]

    def observation_count(self, track_id: int) -> int:
        return len(self._observations.get(track_id, []))

    def aggregate(self, track_id: int) -> AggregatedPlate | None:
        obs_list = self._observations.get(track_id)
        if not obs_list:
            return None

        groups: dict[str, list[float]] = defaultdict(list)
        for obs in obs_list:
            groups[obs.text].append(obs.confidence)

        best_text, best_confs = max(groups.items(), key=lambda kv: sum(kv[1]))
        mean_conf = sum(best_confs) / len(best_confs)
        confirmed = len(best_confs) >= self.vote_min_observations and mean_conf >= self.confirm_min_mean_confidence

        return AggregatedPlate(
            text=best_text,
            mean_confidence=round(mean_conf, 1),
            observation_count=len(best_confs),
            total_observation_count=len(obs_list),
            confirmed=confirmed,
        )

    def all_track_ids(self) -> list[int]:
        return list(self._observations.keys())
