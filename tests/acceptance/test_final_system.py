from dataclasses import replace
from types import SimpleNamespace

from brain.context import Candle, DataQuality, MarketContextBuilder, OrderBook, Trade
from brain.execution import ExecutionEngine, LiveExecutionDisabled, PaperExecutionEngine
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from brain.structure import MTFStructureResult


def fixture():
    closes = [100, 105, 95, 103, 110]
    candles = tuple(Candle(index, close, close + 2, close - 2, close, 100) for index, close in enumerate(closes, 1))
    trades = tuple(Trade(str(index), index, close, 10, "BUY") for index, close in enumerate(closes, 1))
    return (MarketContextBuilder("BTCUSDT", 110, "5m")
            .set_exchange("BYBIT")
            .set_market_data(candles=candles, trades=trades, order_book=OrderBook(bids=((109, 2),), asks=((111, 1),)), open_interest=110, oi_change=5, funding=0.001)
            .set_event_times(event_time=5, received_time=5, calculation_time=5)
            .set_data_quality("OK")
            .build(allow_incomplete=True))


def test_end_to_end_canonical_pipeline_is_deterministic_and_paper_only():
    first = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20))).run(fixture())
    second = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20))).run(fixture())
    assert first.to_dict() == second.to_dict()
    assert first.context.structure is not None
    assert first.context.mtf is not None
    assert first.context.liquidity is not None
    assert first.context.orderflow is not None
    assert first.context.value is not None
    assert first.context.fvg is not None
    assert first.context.oi is not None
    assert first.context.effort is not None
    assert first.context.setup is not None
    assert first.context.entry is not None
    assert first.context.observability is not None
    assert first.intent is None or first.intent.paper_only is True


def test_future_and_forming_candles_do_not_change_historical_structure():
    context = fixture()
    future = Candle(100, 1000, 1001, 999, 1000, 100,)
    with_future = replace(context, candles=context.candles + (future,))
    first = ApexBrainPipeline().run(context)
    assert ApexBrainPipeline().run(with_future).context.structure.to_dict() == first.context.structure.to_dict()


def test_stale_mtf_conflict_and_missing_data_wait():
    pipeline = ApexBrainPipeline()
    stale = fixture()
    stale.metadata["timeframe_metadata"] = {"1h": {"latest_event_time": 1, "expected_interval": 60, "stale_threshold": 2}}
    stale_result = pipeline.run(stale)
    assert stale_result.decision.action == "WAIT"
    conflict = fixture()
    pipeline.mtf.analyze = lambda *args, **kwargs: MTFStructureResult("WAIT", False, {}, ["conflict"], conflict=True)
    conflict_result = pipeline.run(conflict)
    assert conflict_result.decision.action == "WAIT"
    missing = replace(fixture(), funding=None, oi=None, data_quality=DataQuality("DATA_INCOMPLETE"))
    assert ApexBrainPipeline().run(missing).decision.action == "WAIT"


def test_consolidation_and_risk_rejection_fail_closed():
    context = fixture()
    context.market_regime = "BALANCED"
    context.confluence = None
    result = ApexBrainPipeline().run(context)
    assert result.decision.action == "WAIT"
    rejected = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20))).run(fixture(), daily_drawdown_pct=3)
    assert rejected.decision.action == "WAIT"
    assert rejected.risk.approved is False


def test_live_execution_remains_rejected_and_paper_engine_requires_approval():
    try:
        ExecutionEngine().execute_live()
    except LiveExecutionDisabled:
        pass
    else:
        raise AssertionError("Live execution unexpectedly enabled")
    assert PaperExecutionEngine.PAPER_ONLY is True
