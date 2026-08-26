from brain.structure import MultiTimeframeStructure


def test_stale_required_timeframe_is_explicit():
    result = MultiTimeframeStructure().analyze(
        {},
        as_of=100,
        timeframe_metadata={
            "1h": {
                "latest_event_time": 1,
                "expected_interval": 60,
                "stale_threshold": 120,
            }
        },
    )
    assert result.stale is False

    result = MultiTimeframeStructure().analyze(
        {},
        as_of=200,
        timeframe_metadata={
            "1h": {
                "latest_event_time": 1,
                "expected_interval": 60,
                "stale_threshold": 120,
            }
        },
    )
    assert result.stale is True
    assert result.stale_timeframes == ["1h"]
    assert result.bias == "WAIT"
    assert result.aligned is False