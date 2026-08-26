from brain.confluence import ConfluenceEngine
from brain.context import Candle, MarketContextBuilder, OrderBook, Trade
from brain.liquidity import LiquidityEngine, LiquidityResult, LiquiditySweep
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from market.bybit.public_ws import BybitPublicFeed, normalize_bybit_interval
from market.integration.price_history import PriceHistory


def test_bybit_intervals_normalize_to_canonical_names():
    assert normalize_bybit_interval("60") == "1h"
    assert normalize_bybit_interval("240") == "4h"
    assert normalize_bybit_interval("D") == "1d"


def test_price_history_is_event_time_bounded_and_deterministic():
    history = PriceHistory()
    history.ingest(10, 100)
    history.ingest(20, 105)
    history.ingest(20, 999)
    history.ingest(30, 110)
    assert history.state(20).change_pct == 5.0
    assert history.state(25).price == 105
    assert history.state(10).change_pct is None
    assert history.observations == ((10.0, 100.0), (20.0, 105.0), (30.0, 110.0))


def _context(*, imbalance=None, price_change=5.0, oi_change=10.0):
    book = None if imbalance is None else OrderBook(
        bids=((101.0, 10.0 if imbalance > 0 else 1.0),),
        asks=((102.0, 1.0 if imbalance > 0 else (1.0 if imbalance == 0 else 10.0)),),
    )
    candles = tuple(
        Candle(float(index), close, close + 1, close - 1, close, 10)
        for index, close in ((1, 100.0), (2, 105.0), (3, 110.0))
    )
    trades = (Trade("t1", 3, 110, 1, "BUY"),)
    return (MarketContextBuilder("BTCUSDT", 110, "5m")
            .set_exchange("BYBIT")
            .set_price(110)
            .set_price_change_pct(price_change)
            .set_market_data(candles=candles, order_book=book, trades=trades,
                             open_interest=110, oi_change=oi_change)
            .set_event_times(event_time=3, received_time=3, calculation_time=3)
            .set_data_quality("OK")
            .build(allow_incomplete=True))


def test_pipeline_uses_canonical_book_imbalance_for_microstructure():
    pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20)))
    bullish = pipeline.run(_context(imbalance=1.0))
    bearish = pipeline.run(_context(imbalance=-1.0))
    neutral = pipeline.run(_context(imbalance=0.0))
    missing = pipeline.run(_context(imbalance=None))
    assert bullish.context.microstructure.book_bias == "bullish"
    assert bearish.context.microstructure.book_bias == "bearish"
    assert neutral.context.microstructure.book_bias == "neutral"
    assert missing.context.microstructure.book_bias == "neutral"
    assert missing.context.order_book is None


def test_oi_signal_is_directional_only_with_real_price_change():
    pipeline = ApexBrainPipeline()
    result = pipeline.run(_context(imbalance=0.0))
    oi_signals = [signal for signal in result.context.confluence.signals if signal.name == "Open Interest"]
    assert len(oi_signals) == 1
    assert oi_signals[0].direction == "BULLISH"
    assert oi_signals[0].metadata["price_change_pct"] == 5.0
    assert oi_signals[0].metadata["oi_change_pct"] == 10.0
    unavailable = pipeline.run(_context(imbalance=0.0, price_change=None))
    assert not any(signal.name == "Open Interest" for signal in unavailable.context.confluence.signals)


def test_liquidity_cutoff_and_unconfirmed_sweep_do_not_contribute():
    candles = [
        {"event_time": 1, "open": 99, "high": 100, "low": 95, "close": 99},
        {"event_time": 2, "open": 100, "high": 101, "low": 96, "close": 100},
        {"event_time": 3, "open": 99, "high": 100, "low": 94, "close": 99},
        {"event_time": 4, "open": 99, "high": 102, "low": 97, "close": 101},
    ]
    engine = LiquidityEngine()
    historical = engine.analyze(candles, as_of=3)
    repeated = engine.analyze(candles, as_of=3)
    future = engine.analyze(candles, as_of=2)
    assert historical.to_dict() == repeated.to_dict()
    assert future.to_dict() != historical.to_dict()
    assert historical.latest_sweep is None or historical.latest_sweep.displacement


def test_canonical_oi_signal_has_bounded_weight():
    signal = ConfluenceEngine().oi(
        "BULLISH", confidence=100, price_change_pct=5, oi_change_pct=10,
        interpretation="LONG_BUILDUP", event_time=20,
    )
    assert signal.score <= 10
    assert signal.metadata["event_time"] == 20


def test_pipeline_excludes_unconfirmed_liquidity_sweep_signal(monkeypatch):
    pipeline = ApexBrainPipeline()
    sweep = LiquiditySweep("BULLISH", "SELL_SIDE", 100, 99, 101, 2, 1, False)
    result = LiquidityResult([], [], [sweep], sweep, "LONG", 70, [])
    monkeypatch.setattr(pipeline.liquidity, "analyze", lambda candles, as_of=None: result)
    output = pipeline.run(_context(imbalance=0.0))
    assert not any(signal.name == "Liquidity Sweep" for signal in output.context.confluence.signals)
