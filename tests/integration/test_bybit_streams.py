from market.bybit.public_ws import BybitPublicFeed


def test_kline_and_oi_parsers_preserve_unavailable_change():
    feed = BybitPublicFeed()
    feed._process_message({
        "topic": "kline.1.BTCUSDT",
        "data": [{"start": "1000", "open": "100", "high": "102", "low": "99", "close": "101", "volume": "4"}],
    })
    feed._process_message({"topic": "tickers.BTCUSDT", "ts": 1000, "data": {"openInterest": "10", "fundingRate": "0.001"}})
    assert feed.data.candles[0]["close"] == 101
    assert feed.data.open_interest == 10
    assert feed.data.oi_change_pct is None
    feed._process_message({"topic": "tickers.BTCUSDT", "ts": 2000, "data": {"openInterest": "11"}})
    assert feed.data.oi_change_pct == 10


def test_feed_validates_recovery_and_preserves_confirmed_candles():
    feed = BybitPublicFeed(stale_thresholds={"orderbook": 2, "funding": 2, "oi": 2})
    feed._process_message({"topic": "orderbook.50.BTCUSDT", "type": "snapshot", "ts": 1000,
                           "data": {"u": 10, "b": [[99, 2]], "a": [[101, 3]]}}, received_time=1)
    feed._process_message({"topic": "orderbook.50.BTCUSDT", "type": "delta", "ts": 2000,
                           "data": {"u": 11, "pu": 10, "b": [[99, 1]], "a": []}}, received_time=2)
    feed._process_message({"topic": "kline.5.BTCUSDT", "ts": 3000,
                           "data": [{"start": "3000", "open": "100", "high": "103", "low": "99",
                                     "close": "102", "volume": "7", "confirm": False}]}, received_time=3)
    assert feed.data.book_ready is True
    assert feed.data.candles_by_timeframe["5m"][0]["confirmed"] is False
    assert feed.data.quality(now=3)[0] == "DATA_INCOMPLETE"


def test_feed_rejects_crossed_book_and_sequence_gap():
    feed = BybitPublicFeed()
    feed._process_message({"topic": "orderbook.50.BTCUSDT", "type": "snapshot", "ts": 1000,
                           "data": {"u": 10, "b": [[99, 2]], "a": [[101, 3]]}})
    feed._process_message({"topic": "orderbook.50.BTCUSDT", "type": "delta", "ts": 2000,
                           "data": {"u": 12, "pu": 10, "b": [[102, 1]], "a": []}})
    assert feed.data.data_quality == "DATA_INVALID"
    assert feed.data.book_ready is False


def test_reconnect_preserves_oi_and_trades_but_requires_fresh_book():
    feed = BybitPublicFeed()
    feed._process_message({"topic": "tickers.BTCUSDT", "ts": 10000,
                           "data": {"openInterest": "100"}})
    feed._process_message({"topic": "tickers.BTCUSDT", "ts": 20000,
                           "data": {"openInterest": "110"}})
    feed._process_message({"topic": "publicTrade.BTCUSDT", "data": [
        {"i": "trade-1", "T": 20000, "p": "100", "v": "2", "S": "Buy"}
    ]})
    feed._process_message({"topic": "orderbook.50.BTCUSDT", "type": "snapshot", "ts": 20000,
                           "data": {"u": 10, "b": [[99, 2]], "a": [[101, 3]]}})

    feed._reset_state()

    assert feed.data.book_ready is False
    assert feed.data.last_sequence is None
    assert [timestamp for timestamp, _ in sorted(feed.oi_history._observations.items())] == [10.0, 20.0]
    feed._process_message({"topic": "tickers.BTCUSDT", "ts": 30000,
                           "data": {"openInterest": "121"}})
    assert feed.data.oi_change_pct == 10.0
    assert list(feed.oi_history._observations) == [10.0, 20.0, 30.0]
    assert [trade["id"] for trade in feed.data.trades] == ["trade-1"]

    feed._process_message({"topic": "orderbook.50.BTCUSDT", "type": "delta", "ts": 30000,
                           "data": {"u": 11, "pu": 10, "b": [[99, 1]], "a": []}})
    assert feed.data.book_ready is False
    assert feed.data.data_quality == "DATA_INVALID"

    feed._process_message({"topic": "orderbook.50.BTCUSDT", "type": "snapshot", "ts": 30000,
                           "data": {"u": 20, "b": [[98, 2]], "a": [[102, 3]]}})
    assert feed.data.book_ready is True
    assert feed.data.last_sequence == 20


def test_disconnect_immediately_invalidates_market_data():
    feed = BybitPublicFeed()
    feed._process_message({"topic": "orderbook.50.BTCUSDT", "type": "snapshot", "ts": 1000,
                           "data": {"u": 10, "b": [[99, 2]], "a": [[101, 3]]}})
    feed._mark_disconnected("test disconnect")
    assert feed.data.continuity_status == "DISCONNECTED"
    assert feed.data.book_ready is False
    assert feed.data.quality()[0] != "DATA_VALID"


def test_timestamp_less_funding_is_stale():
    feed = BybitPublicFeed()
    feed._process_message({"topic": "tickers.BTCUSDT", "data": {"fundingRate": "0.001"}})
    assert feed.data.funding_rate == 0.001
    assert feed.data.funding_stale is True