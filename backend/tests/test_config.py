import pytest

from backend.config import PersonIDConfig


def test_resolve_votes_single_reference_never_crashes():
    # A single usable reference photo must not require the configured
    # multi-reference min_votes=2 - it should adapt down to 1.
    assert PersonIDConfig.resolve_votes(configured_min_votes=2, usable_reference_count=1) == 1


def test_resolve_votes_multi_reference_uses_configured_min():
    assert PersonIDConfig.resolve_votes(configured_min_votes=2, usable_reference_count=5) == 2


def test_resolve_votes_caps_at_usable_count_when_fewer_than_configured():
    # configured min_votes higher than usable references still can't exceed usable count
    assert PersonIDConfig.resolve_votes(configured_min_votes=4, usable_reference_count=2) == 2


def test_resolve_votes_zero_usable_raises():
    with pytest.raises(ValueError):
        PersonIDConfig.resolve_votes(configured_min_votes=2, usable_reference_count=0)
