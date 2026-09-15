"""Zone-crossing intent forecasting: predicts whether/when an approaching
track will cross into a zone BEFORE it actually happens, instead of only
reacting once ZoneMonitor commits a real ZONE_ENTRY.

Method: linear extrapolation. Over a short trailing window of a track's
footpoints, fit its average velocity (least-squares over the window - robust
to one noisy sample, unlike a bare last-two-points difference), then treat
the track's future position as a ray leaving its current point along that
velocity. If that ray hits an edge of the zone polygon within
`horizon_sec`, emit one PREDICTED_ZONE_CROSSING event carrying the
projected ETA (in seconds) and the point on the boundary it's heading for.

Deliberately zero cv2/ultralytics/torch dependency (pure Python, only
depends on zone/geometry.py), same philosophy as zone/state.py, so it's
unit-testable without real video or CV models.

Coordinate space: same convention as ZoneMonitor - whatever space the
caller's footpoints and polygon are already in (this project always calls
it with pixel-space footpoints and a pixel-space denormalized polygon, same
as ZoneMonitor.update), so ETA and speed thresholds come out in seconds and
pixels/sec respectively, consistent with BehaviorConfig's own pixel-space,
resolution-dependent thresholds.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class ForecastEvent:
    type: str  # "PREDICTED_ZONE_CROSSING"
    zone_id: str
    track_id: int
    frame_index: int
    timestamp_sec: float
    data: dict = field(default_factory=dict)


@dataclass
class _TrackHistory:
    points: deque = field(default_factory=lambda: deque(maxlen=8))  # (timestamp_sec, x, y)
    warned: bool = False
    last_warning_ts: float | None = None


def _fit_velocity(points: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    """Least-squares velocity (vx, vy), in units/sec, from trailing (t, x, y)
    samples. None if there aren't enough samples or they span ~zero time
    (e.g. duplicate timestamps)."""
    n = len(points)
    if n < 2:
        return None
    t0 = points[0][0]
    ts = [p[0] - t0 for p in points]
    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    t_mean = sum(ts) / n
    denom = sum((t - t_mean) ** 2 for t in ts)
    if denom < 1e-9:
        return None
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    vx = sum((t - t_mean) * (x - x_mean) for t, x in zip(ts, xs)) / denom
    vy = sum((t - t_mean) * (y - y_mean) for t, y in zip(ts, ys)) / denom
    return vx, vy


def project_forward(origin: tuple[float, float], velocity: tuple[float, float], seconds: float) -> tuple[float, float]:
    """Where a track would be after `seconds` at constant `velocity` -
    exposed for annotation (drawing the projected path)."""
    ox, oy = origin
    vx, vy = velocity
    return (ox + vx * seconds, oy + vy * seconds)


def _ray_polygon_eta(origin: tuple[float, float], velocity: tuple[float, float], polygon: list[tuple[float, float]]) -> float | None:
    """Seconds until the ray `origin + t*velocity` (t >= 0) first crosses an
    edge of the closed polygon ring. None if it never will (velocity is
    zero, or points away from every edge)."""
    ox, oy = origin
    dx, dy = velocity
    if dx == 0.0 and dy == 0.0:
        return None
    best_t = None
    n = len(polygon)
    for i in range(n):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        rx, ry = ax - ox, ay - oy
        denom = ex * dy - ey * dx
        if abs(denom) < 1e-9:
            continue  # parallel to this edge
        t = (ex * ry - ey * rx) / denom
        s = (dx * ry - dy * rx) / denom
        if t >= 0.0 and 0.0 <= s <= 1.0 and (best_t is None or t < best_t):
            best_t = t
    return best_t


class ZoneForecaster:
    """One instance per zone, mirroring ZoneMonitor's one-instance-per-zone
    convention. Independent per-track trajectory history keyed by track_id."""

    def __init__(
        self,
        zone_id: str,
        horizon_sec: float = 5.0,
        history_frames: int = 8,
        min_speed_px_per_sec: float = 15.0,
        rewarn_cooldown_sec: float = 8.0,
    ):
        self.zone_id = zone_id
        self.horizon_sec = horizon_sec
        self.history_frames = max(2, history_frames)
        self.min_speed_px_per_sec = min_speed_px_per_sec
        self.rewarn_cooldown_sec = rewarn_cooldown_sec
        self._history: dict[int, _TrackHistory] = {}
        self.events: list[ForecastEvent] = []

    def predicted_target(self, track_id: int) -> tuple[float, float] | None:
        """Current best-fit velocity for a track, or None - lets callers
        (annotation code) draw the same projected path the forecast used."""
        hist = self._history.get(track_id)
        if hist is None:
            return None
        return _fit_velocity(list(hist.points))

    def update(
        self,
        active_points: dict[int, tuple[float, float]],
        currently_inside: set[int],
        frame_index: int,
        timestamp_sec: float,
        polygon: list[tuple[float, float]],
    ) -> None:
        """Advance one frame. `active_points` is the same footpoint map
        passed to ZoneMonitor.update this frame; `currently_inside` is the
        set of track_ids ZoneMonitor already considers INSIDE this zone
        (after its own update) - those are skipped since they've already
        crossed, and their history resets so a later exit-and-reapproach can
        warn again."""
        seen = set(active_points)
        for tid in list(self._history):
            if tid not in seen:
                del self._history[tid]  # bound memory for gone tracks

        for tid, point in active_points.items():
            hist = self._history.setdefault(tid, _TrackHistory())
            hist.points.append((timestamp_sec, point[0], point[1]))

            if tid in currently_inside:
                hist.warned = False  # reset so a future exit + reapproach can warn again
                continue

            velocity = _fit_velocity(list(hist.points))
            if velocity is None:
                continue
            speed = (velocity[0] ** 2 + velocity[1] ** 2) ** 0.5
            if speed < self.min_speed_px_per_sec:
                continue  # near-stationary - extrapolating noise would be meaningless

            eta = _ray_polygon_eta(point, velocity, polygon)
            if eta is None or eta > self.horizon_sec:
                if hist.warned and (eta is None or eta > self.horizon_sec * 1.5):
                    hist.warned = False  # trajectory diverged well clear of the zone - allow re-arm
                continue

            if hist.warned and hist.last_warning_ts is not None and timestamp_sec - hist.last_warning_ts < self.rewarn_cooldown_sec:
                continue  # already warned about this approach recently

            hist.warned = True
            hist.last_warning_ts = timestamp_sec
            target = project_forward(point, velocity, eta)
            self.events.append(ForecastEvent(
                "PREDICTED_ZONE_CROSSING", self.zone_id, tid, frame_index, timestamp_sec,
                {"eta_sec": round(eta, 2), "predicted_point": [round(target[0]), round(target[1])]},
            ))
