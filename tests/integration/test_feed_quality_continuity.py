from market.bybit.public_ws import BybitPublicFeed


def message(sequence, previous=None):
    data = {"u": sequence, "b": [[99, 2]], "a": [[101, 2]]}
    if previous is not None:
        data["pu"] = previous
    return {"topic": "orderbook.50.BTCUSDT", "type": "delta", "ts": sequence * 1000, "data": data}


def test_feed_labels_normal_duplicate_gap_and_regression():
    feed = BybitPublicFeed()
    feed._process_message({**message(1), "type": "snapshot"})
    feed._process_message(message(2, 1))
    assert feed.data.continuity_status == "HEALTHY"
    feed._process_message(message(2, 1))
    assert feed.data.continuity_status == "OUT_OF_ORDER"
    feed = BybitPublicFeed()
    feed._process_message({**message(1), "type": "snapshot"})
    feed._process_message(message(4, 1))
    assert feed.data.continuity_status == "SEQUENCE_GAP"


def test_feed_rejects_wrong_symbol_and_reconnect_requires_snapshot():
    feed = BybitPublicFeed()
    feed._process_message({"topic": "orderbook.50.ETHUSDT", "type": "snapshot", "ts": 1,
                           "data": {"u": 1, "b": [[99, 1]], "a": [[101, 1]]}})
    assert feed.data.data_quality == "DATA_INVALID"
    feed._process_message({**message(1), "type": "snapshot"})
    feed._reset_state()
    assert feed.data.continuity_status == "RECONNECTING"
    feed._process_message(message(2, 1))
    assert feed.data.book_ready is False
    assert feed.data.continuity_status == "SEQUENCE_GAP"