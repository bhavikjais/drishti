import pytest

from backend.modules.zone.geometry import (
    Zone, centroid, denormalize_polygon, footpoint, point_in_polygon,
)


def test_point_inside_rectangle():
    rect = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((5, 5), rect) is True


def test_point_outside_rectangle():
    rect = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((15, 5), rect) is False
    assert point_in_polygon((-5, 5), rect) is False


def test_point_inside_polygon():
    triangle = [(0, 0), (10, 0), (5, 10)]
    assert point_in_polygon((5, 3), triangle) is True
    assert point_in_polygon((1, 8), triangle) is False  # outside the triangle's slanted edge


def test_zone_rectangle_expands_to_4_point_polygon():
    zone = Zone(zone_id="z1", video_id="v1", label="Restricted", shape="rectangle", points=[(0.1, 0.1), (0.5, 0.5)])
    poly = zone.normalized_polygon()
    assert poly == [(0.1, 0.1), (0.5, 0.1), (0.5, 0.5), (0.1, 0.5)]


def test_zone_polygon_passes_through_unchanged():
    pts = [(0.1, 0.1), (0.5, 0.2), (0.4, 0.6)]
    zone = Zone(zone_id="z2", video_id="v1", label="Zone", shape="polygon", points=pts)
    assert zone.normalized_polygon() == pts


def test_zone_rejects_out_of_range_coordinates():
    with pytest.raises(ValueError):
        Zone(zone_id="z3", video_id="v1", label="bad", shape="rectangle", points=[(0.1, 0.1), (1.5, 0.5)])


def test_zone_rejects_too_few_polygon_points():
    with pytest.raises(ValueError):
        Zone(zone_id="z4", video_id="v1", label="bad", shape="polygon", points=[(0.1, 0.1), (0.2, 0.2)])


def test_denormalize_polygon_maps_to_pixel_resolution():
    norm = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    px = denormalize_polygon(norm, width=1920, height=1080)
    assert px == [(0, 0), (1920, 0), (1920, 1080), (0, 1080)]


def test_normalized_zone_survives_different_output_resolution():
    # a zone drawn on a 640x360 representative frame must land in the same
    # relative place if the video is processed/output at 1920x1080
    zone = Zone(zone_id="z5", video_id="v1", label="Zone", shape="rectangle", points=[(0.25, 0.25), (0.75, 0.75)])
    poly = zone.normalized_polygon()
    px_small = denormalize_polygon(poly, 640, 360)
    px_large = denormalize_polygon(poly, 1920, 1080)
    # relative position (fraction of width/height) must match at both resolutions
    for (xs, ys), (xl, yl) in zip(px_small, px_large):
        assert abs(xs / 640 - xl / 1920) < 1e-6
        assert abs(ys / 360 - yl / 1080) < 1e-6


def test_footpoint_is_bottom_center():
    assert footpoint((10, 20, 30, 60)) == (20.0, 60)


def test_centroid_is_box_center():
    assert centroid((10, 20, 30, 60)) == (20.0, 40.0)
