from market.integration.data_quality import DataQualityEngine


def test_trade_history_reports_duplicate_regression_and_symbol():
    engine = DataQualityEngine()
    results = engine.validate([
        {"kind": "trade", "id": "t1", "event_time": 1, "symbol": "BTCUSDT", "price": 100, "quantity": 1, "side": "BUY"},
        {"kind": "trade", "id": "t1", "event_time": 2, "symbol": "BTCUSDT", "price": 100, "quantity": 1, "side": "BUY"},
        {"kind": "trade", "id": "t2", "event_time": 0, "symbol": "ETHUSDT", "price": 100, "quantity": 1, "side": "BUY"},
    ], symbol="BTCUSDT")
    assert results[1].status == "DUPLICATE"
    assert results[1].reason_codes == ("DUPLICATE_EVENT",)
    assert results[2].status == "INVALID"
    assert "SYMBOL_MISMATCH" in results[2].reason_codes
    assert "NON_MONOTONIC_EVENT_SEQUENCE" in results[2].reason_codes


def test_candle_history_reports_timeframe_unit_and_stale_failures():
    engine = DataQualityEngine()
    assert "TIMEFRAME_MISMATCH" in engine.validate_event(
        {"kind": "candle", "event_time": 1, "timeframe": "5m"}, timeframe="1m"
    ).reason_codes
    assert "TIMESTAMP_UNIT_MISMATCH" in engine.validate_event(
        {"kind": "candle", "event_time": 1_700_000_000_000, "timestamp_unit": "seconds"}
    ).reason_codes
    stale = engine.validate_event({"kind": "candle", "event_time": 1, "stale": True})
    assert stale.status == "STALE"
    assert stale.reason_codes == ("STALE_EVENT",)


def test_order_book_history_reports_crossing_conflict_and_reconnect():
    engine = DataQualityEngine()
    crossed = engine.validate_event({
        "kind": "orderbook", "event_time": 2, "bids": [[101, 1]], "asks": [[100, 1]],
    })
    assert crossed.status == "INVALID"
    assert "CROSSED_BOOK" in crossed.reason_codes
    conflict = engine.validate_event({
        "kind": "orderbook", "event_time": 3, "bids": [[99, 1]], "asks": [[101, 1]],
        "conflicting_snapshot": True, "conflicting_record": True,
    })
    assert "CONFLICTING_RECORD" in conflict.reason_codes
    reconnect = engine.validate_event({
        "kind": "orderbook", "event_time": 4, "bids": [[99, 1]], "asks": [[101, 1]],
        "reconnect": True, "reconnect_required": True,
    })
    assert "RECONNECT_REQUIRED" in reconnect.reason_codes


def test_oi_and_funding_history_report_invalid_future_and_cutoff_visibility():
    engine = DataQualityEngine()
    assert "INVALID_VALUE" in engine.validate_event(
        {"kind": "oi", "event_time": 1, "value": -1}, symbol="BTCUSDT"
    ).reason_codes
    assert "SYMBOL_MISMATCH" in engine.validate_event(
        {"kind": "funding", "event_time": 1, "symbol": "ETHUSDT", "value": 0.01}, symbol="BTCUSDT"
    ).reason_codes
    results = engine.validate([
        {"kind": "funding", "event_time": 1, "value": 0.01},
        {"kind": "funding", "event_time": 3, "value": "bad"},
    ], as_of=2)
    assert results[0].status == "VALID"
    assert results[1].status == "FUTURE"
    assert results[1].reason_codes == ("FUTURE_EVENT",)


def test_historical_invalid_events_are_not_hidden_by_future_cutoff_records():
    engine = DataQualityEngine()
    results = engine.validate([
        {"kind": "trade", "event_time": 1, "price": 0, "quantity": 1, "side": "BUY"},
        {"kind": "trade", "event_time": 10, "price": 100, "quantity": 1, "side": "BUY"},
    ], as_of=5)
    assert results[0].status == "INVALID"
    assert "INVALID_PRICE" in results[0].reason_codes
    assert results[1].status == "FUTURE"


def test_quality_results_are_deterministic():
    events = [
        {"kind": "oi", "id": "oi-1", "event_time": 2, "value": 100},
        {"kind": "oi", "id": "oi-1", "event_time": 2, "value": 100},
    ]
    engine = DataQualityEngine()
    assert [item.to_dict() for item in engine.validate(events)] == [item.to_dict() for item in engine.validate(events)]
