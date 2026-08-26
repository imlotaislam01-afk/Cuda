from market.integration.context_adapter import LiveSnapshotContextAdapter
from market.integration.funding_history import FundingHistory
from market.integration.live_snapshot import LiveMarketSnapshot


def test_funding_history_orders_deduplicates_and_respects_exact_cutoff():
    history = FundingHistory("BTCUSDT", stale_after=10)
    history.ingest(20, 0.02)
    history.ingest(10, 0.01)
    history.ingest(20, 0.03)

    assert history.state(10).funding_rate == 0.01
    assert history.state(20).funding_rate == 0.02
    assert history.state(19.999).funding_rate == 0.01
    assert history.latest().funding_rate == 0.02
    assert history.observations == ((10.0, 0.01), (20.0, 0.02))


def test_funding_history_empty_and_stale_states_are_explicit():
    history = FundingHistory("BTCUSDT", stale_after=5)
    empty = history.state(10)
    assert empty.symbol == "BTCUSDT"
    assert empty.funding_rate is None
    assert empty.stale is True

    history.ingest(1, 0.01)
    assert history.state(7).stale is True


def test_funding_state_exposes_event_time_safe_positioning_facts():
    history = FundingHistory("BTCUSDT", extreme_positive=0.01)
    history.ingest(10, 0.001)
    history.ingest(20, 0.004)
    history.ingest(30, 0.014)

    state = history.state(30)

    assert state.direction == "POSITIVE"
    assert state.extreme is True
    assert state.velocity == 0.001
    assert state.acceleration == 0.0007
    assert history.state(20).extreme is False


def test_funding_thresholds_reject_invalid_configuration():
    try:
        FundingHistory("BTCUSDT", extreme_positive=-0.01, extreme_negative=0.01)
    except ValueError as exc:
        assert "threshold" in str(exc)
    else:
        raise AssertionError("Expected invalid funding thresholds to be rejected")


def test_adapter_uses_historical_funding_instead_of_latest_value():
    snapshot = LiveMarketSnapshot("BTCUSDT")
    snapshot.feed.data.symbol = "BTCUSDT"
    snapshot.feed.data.price = 100.0
    snapshot.feed.data.bids = {99.0: 2.0}
    snapshot.feed.data.asks = {101.0: 2.0}
    snapshot.feed.data.data_quality = "OK"
    snapshot.feed.data.last_update = 20.0
    snapshot.feed.data.last_event_time = 20.0
    snapshot.feed.data.orderbook_event_time = 20.0
    snapshot.feed.data.book_ready = True
    snapshot.feed.oi_history.ingest(10, 100)
    snapshot.feed.data.open_interest = 100
    snapshot.feed.data.oi_event_time = 10
    snapshot.feed.funding_history.ingest(10, 0.001)
    snapshot.feed.funding_history.ingest(20, 0.02)
    snapshot.feed.data.funding_rate = 0.02
    snapshot.feed.data.funding_event_time = 20
    snapshot.feed.data.candles = [{
        "event_time": 10, "open": 100, "high": 101, "low": 99,
        "close": 100, "volume": 10, "confirmed": True,
    }]
    snapshot.feed.price_history.ingest(10, 100)
    snapshot.feed.price_history.ingest(20, 100)

    context = LiveSnapshotContextAdapter(snapshot).build(
        calculation_time=20,
        as_of=10,
    )

    assert context is not None
    assert context.funding == 0.001
    assert context.metadata["funding_event_time"] == 10


def test_future_only_funding_is_incomplete_and_cannot_create_context_trade():
    snapshot = LiveMarketSnapshot("BTCUSDT")
    feed = snapshot.feed
    feed._process_message({
        "topic": "orderbook.50.BTCUSDT", "type": "snapshot", "ts": 20_000,
        "data": {"u": 1, "b": [[99, 2]], "a": [[101, 2]]},
    }, received_time=20)
    feed._process_message({
        "topic": "kline.1.BTCUSDT", "ts": 20_000,
        "data": [{"start": 20_000, "open": 100, "high": 101, "low": 99,
                  "close": 100, "volume": 10, "confirm": True}],
    }, received_time=20)
    feed._process_message({
        "topic": "tickers.BTCUSDT", "ts": 20_000,
        "data": {"lastPrice": 100, "openInterest": 100, "fundingRate": 0.02},
    }, received_time=20)

    context = LiveSnapshotContextAdapter(snapshot).build(
        calculation_time=20,
        as_of=10,
    )

    assert context is None