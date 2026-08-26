from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from market.integration.live_snapshot import LiveMarketSnapshot


def _message(event_time, topic, data, kind="delta"):
    return {
        "topic": topic,
        "type": kind,
        "ts": int(event_time * 1000),
        "data": data,
    }


def _feed_events():
    values = [(10, 5, 8), (12, 6, 11), (9, 4, 7), (13, 7, 12),
              (11, 6, 10), (15, 8, 14), (14, 9, 13), (16, 10, 16)]
    events = [
        _message(1, "orderbook.50.BTCUSDT", {
            "u": 1, "b": [[99, 2]], "a": [[101, 2]],
        }, "snapshot"),
        _message(2, "orderbook.50.BTCUSDT", {
            "u": 2, "pu": 1, "b": [[99, 3]], "a": [],
        }),
    ]
    for index, (high, low, close) in enumerate(values, 2):
        events.append(_message(index, "kline.1.BTCUSDT", [{
            "start": index * 1000,
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": 10,
            "confirm": True,
        }]))
    events.extend([
        _message(3, "kline.5.BTCUSDT", [{
            "start": 3000, "open": 10, "high": 12, "low": 8,
            "close": 11, "volume": 25, "confirm": True,
        }]),
        _message(4, "kline.60.BTCUSDT", [{
            "start": 4000, "open": 10, "high": 13, "low": 7,
            "close": 12, "volume": 30, "confirm": True,
        }]),
        _message(5, "kline.240.BTCUSDT", [{
            "start": 5000, "open": 10, "high": 14, "low": 6,
            "close": 13, "volume": 40, "confirm": True,
        }]),
        _message(6, "kline.5.BTCUSDT", [{
            "start": 6000, "open": 10, "high": 14, "low": 7,
            "close": 12, "volume": 20, "confirm": False,
        }]),
        _message(8, "publicTrade.BTCUSDT", [{
            "i": "trade-1", "T": 8000, "p": 16, "v": 20, "S": "Buy",
        }]),
        _message(9, "tickers.BTCUSDT", {
            "lastPrice": "16", "openInterest": "90", "fundingRate": "0.001",
        }),
        _message(12, "publicTrade.BTCUSDT", [{
            "i": "future-trade", "T": 12000, "p": 17, "v": 50, "S": "Sell",
        }]),
        _message(12, "kline.5.BTCUSDT", [{
            "start": 12000, "open": 10, "high": 20, "low": 5,
            "close": 17, "volume": 100, "confirm": True,
        }]),
        _message(13, "tickers.BTCUSDT", {
            "lastPrice": "17", "openInterest": "100",
        }),
    ])
    return events


def test_real_live_entrypoint_reaches_canonical_paper_pipeline_deterministically():
    pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20)))
    pipeline.decision.minimum_confidence = 20

    first_snapshot = LiveMarketSnapshot("BTCUSDT")
    for message in _feed_events():
        first_snapshot.feed._process_message(message, received_time=message["ts"] / 1000)
    first = first_snapshot.run_pipeline(pipeline, calculation_time=13, as_of=11)

    second_snapshot = LiveMarketSnapshot("BTCUSDT")
    for message in _feed_events():
        second_snapshot.feed._process_message(message, received_time=message["ts"] / 1000)
    second = second_snapshot.run_pipeline(pipeline, calculation_time=13, as_of=11)

    assert first.context.event_time == 11
    assert first.context.metadata["candles_by_timeframe"]["5m"]
    assert first.context.metadata["candles_by_timeframe"]["1h"]
    assert first.context.metadata["candles_by_timeframe"]["4h"]
    assert all(candle.event_time <= 11 for candle in first.context.candles)
    assert all(candle["event_time"] <= 11 for candle in first.context.metadata["candles_by_timeframe"]["5m"])
    assert all(trade.event_time <= 11 for trade in first.context.trades)
    assert first.context.open_interest == 90
    assert first.context.funding == 0.001
    assert first.context.order_book is not None
    assert first.context.confluence.to_dict() == second.context.confluence.to_dict()
    assert first.decision.to_dict() == second.decision.to_dict()
    assert first.risk.to_dict() == second.risk.to_dict()
    assert first.intent is not None
    assert first.intent.paper_only is True
    assert first.intent.metadata["execution_mode"] == "PAPER_ONLY"


def test_future_orderbook_is_incomplete_and_cannot_create_intent():
    snapshot = LiveMarketSnapshot("BTCUSDT")
    for message in _feed_events():
        snapshot.feed._process_message(message, received_time=message["ts"] / 1000)
    snapshot.feed._process_message(_message(12, "orderbook.50.BTCUSDT", {
        "u": 3, "pu": 2, "b": [[99, 1]], "a": [],
    }), received_time=10)
    snapshot.feed._process_message(_message(12, "tickers.BTCUSDT", {
        "fundingRate": "0.02",
    }), received_time=12)

    result = snapshot.run_pipeline(
        ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20))),
        calculation_time=13,
        as_of=11,
    )

    assert result.context.order_book is None
    assert result.context.data_quality.status == "DATA_INCOMPLETE"
    assert result.intent is None