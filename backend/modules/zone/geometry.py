"""Zone geometry: normalized <-> pixel coordinates, point-in-zone test.

A rectangle is just represented as its 2 opposite corners and expanded to a
4-point polygon internally, so point_in_polygon() is the ONE algorithm that
handles both shapes - no separate rectangle-containment code path to keep in
sync.

Coordinates are stored normalized ([0,1] x [0,1]) so a zone drawn on a
representative frame at one resolution still lines up correctly if the video
is processed/output at a different resolution.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Zone:
    zone_id: str
    video_id: str
    label: str
    shape: str  # "rectangle" | "polygon"
    points: list[tuple[float, float]]  # normalized [0,1]; rectangle: [(x1,y1),(x2,y2)] opposite corners

    def __post_init__(self):
        if self.shape not in ("rectangle", "polygon"):
            raise ValueError(f"unknown zone shape: {self.shape!r}")
        if self.shape == "rectangle" and len(self.points) != 2:
            raise ValueError("rectangle zone requires exactly 2 points (opposite corners)")
        if self.shape == "polygon" and len(self.points) < 3:
            raise ValueError("polygon zone requires at least 3 points")
        for x, y in self.points:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(f"zone points must be normalized to [0,1], got ({x}, {y})")

    def normalized_polygon(self) -> list[tuple[float, float]]:
        """Expands a rectangle's 2 corners into a closed 4-point polygon;
        polygons pass through unchanged."""
        if self.shape == "rectangle":
            (x1, y1), (x2, y2) = self.points
            return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        return list(self.points)

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id, "video_id": self.video_id, "label": self.label,
            "shape": self.shape, "points": [list(p) for p in self.points],
        }

    @staticmethod
    def from_dict(d: dict) -> "Zone":
        return Zone(
            zone_id=d["zone_id"], video_id=d["video_id"], label=d.get("label", ""),
            shape=d["shape"], points=[tuple(p) for p in d["points"]],
        )


def denormalize_polygon(norm_points: list[tuple[float, float]], width: int, height: int) -> list[tuple[int, int]]:
    return [(int(round(x * width)), int(round(y * height))) for x, y in norm_points]


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Standard ray-casting point-in-polygon test. O(n) in vertex count -
    trivially cheap next to detection/tracking, matching the "zone checking
    itself must be cheap" requirement. Boundary points may resolve either way
    (float ray-casting edge case) - callers needing strict inclusivity should
    not rely on exact-boundary behavior.
    """
    x, y = point
    n = len(polygon)
    inside = False
    x1, y1 = polygon[-1]
    for x2, y2 in polygon:
        if ((y1 > y) != (y2 > y)):
            x_intersect = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
            if x < x_intersect:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def footpoint(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    """Bottom-center of a bounding box - approximates where the object
    touches the ground, more accurate than the bbox center for a ground-plane
    zone (a tall person's centroid sits at chest height, not their feet)."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, y2)


def centroid(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
