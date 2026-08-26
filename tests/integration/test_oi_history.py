from market.integration.oi_history import OIHistory


def test_oi_history_is_duplicate_safe_and_chronological():
    history = OIHistory(stale_after=10)
    history.ingest(20, 110)
    history.ingest(10, 100)
    history.ingest(20, 110)

    state = history.state(20)
    assert state.open_interest == 110
    assert state.change_pct == 10
    assert state.stale is False


def test_oi_history_has_no_change_without_previous_observation():
    state = OIHistory().ingest(1, 100)
    assert state.change_pct is None


def test_oi_history_marks_old_observation_stale():
    state = OIHistory(stale_after=5).ingest(1, 100)
    assert OIHistory(stale_after=5).state(10).stale is True
    assert state.stale is False


def test_oi_history_exposes_velocity_spike_and_compression_at_cutoff():
    history = OIHistory(stale_after=10, spike_pct=5, compression_pct=0.25)
    history.ingest(10, 100)
    history.ingest(20, 110)

    state = history.state(20)

    assert state.velocity == 1.0
    assert state.spike is True
    assert state.compression is False
    assert history.state(15).open_interest == 100


def test_oi_history_rejects_mismatched_symbols():
    history = OIHistory(symbol="BTCUSDT")
    history.ingest(1, 100, symbol="BTCUSDT")

    try:
        history.ingest(2, 200, symbol="ETHUSDT")
    except ValueError as exc:
        assert "symbol" in str(exc)
    else:
        raise AssertionError("Expected mismatched OI symbol to be rejected")