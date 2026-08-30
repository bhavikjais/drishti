from backend.modules.anpr.aggregator import PlateAggregator


def make_aggregator(max_obs=20, vote_min=3, min_conf=55.0):
    return PlateAggregator(max_observations_per_track=max_obs, vote_min_observations=vote_min, confirm_min_mean_confidence=min_conf)


def test_no_observations_returns_none():
    agg = make_aggregator()
    assert agg.aggregate(track_id=1) is None


def test_consistent_reads_aggregate_and_confirm():
    # mirrors the spec's worked example: DL01AB1234 read 4 times at
    # 61/78/91/86 -> confirmed, mean ~79
    agg = make_aggregator(vote_min=3, min_conf=55.0)
    for frame_idx, conf in [(120, 61), (125, 78), (130, 91), (135, 86)]:
        agg.add_observation(track_id=27, text="DL01AB1234", confidence=conf, frame_index=frame_idx, timestamp_sec=frame_idx / 25)

    result = agg.aggregate(track_id=27)
    assert result.text == "DL01AB1234"
    assert result.observation_count == 4
    assert result.confirmed is True
    assert 78 <= result.mean_confidence <= 80


def test_single_garbage_frame_does_not_win_over_consistent_majority():
    agg = make_aggregator(vote_min=3, min_conf=55.0)
    for conf in (70, 75, 80):
        agg.add_observation(track_id=1, text="DL01AB1234", confidence=conf, frame_index=0, timestamp_sec=0.0)
    # one bad frame produces total garbage
    agg.add_observation(track_id=1, text="XQ99ZZ0000", confidence=95, frame_index=1, timestamp_sec=0.1)

    result = agg.aggregate(track_id=1)
    assert result.text == "DL01AB1234"  # majority wins despite one high-confidence outlier
    assert result.confirmed is True


def test_not_confirmed_below_min_observation_count():
    agg = make_aggregator(vote_min=3, min_conf=55.0)
    agg.add_observation(track_id=1, text="DL01AB1234", confidence=95, frame_index=0, timestamp_sec=0.0)
    agg.add_observation(track_id=1, text="DL01AB1234", confidence=95, frame_index=1, timestamp_sec=0.1)
    result = agg.aggregate(track_id=1)
    assert result.observation_count == 2
    assert result.confirmed is False  # only 2 observations, vote_min_observations=3


def test_not_confirmed_below_min_mean_confidence():
    agg = make_aggregator(vote_min=2, min_conf=55.0)
    agg.add_observation(track_id=1, text="DL01AB1234", confidence=30, frame_index=0, timestamp_sec=0.0)
    agg.add_observation(track_id=1, text="DL01AB1234", confidence=35, frame_index=1, timestamp_sec=0.1)
    result = agg.aggregate(track_id=1)
    assert result.observation_count == 2
    assert result.confirmed is False  # enough observations, but confidence too low


def test_observation_cap_evicts_oldest():
    agg = make_aggregator(max_obs=3, vote_min=2, min_conf=0.0)
    agg.add_observation(1, "AAA111", 90, 0, 0.0)
    agg.add_observation(1, "AAA111", 90, 1, 0.1)
    agg.add_observation(1, "AAA111", 90, 2, 0.2)
    agg.add_observation(1, "BBB222", 99, 3, 0.3)  # pushes out the oldest AAA111 observation
    result = agg.aggregate(1)
    assert agg.observation_count(1) == 3
    # AAA111 now has 2 observations, BBB222 has 1 - AAA111 still wins on total confidence
    assert result.text == "AAA111"


def test_tracks_are_independent():
    agg = make_aggregator(vote_min=1, min_conf=0.0)
    agg.add_observation(1, "AAA111", 90, 0, 0.0)
    agg.add_observation(2, "BBB222", 90, 0, 0.0)
    assert agg.aggregate(1).text == "AAA111"
    assert agg.aggregate(2).text == "BBB222"
