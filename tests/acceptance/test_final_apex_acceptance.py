from dataclasses import replace

import pytest

from brain.context import Candle, DataQuality
from brain.execution import ExecutionIntentBuilder, PaperExecutionEngine
from brain.fvg import OrderBlockEngine
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from market.integration.data_quality import DataQualityEngine
from market.replay import RawBybitReplayHarness

from tests.replay.test_raw_bybit_replay import pipeline as acceptance_pipeline
from tests.replay.test_raw_bybit_replay import raw_fixture


def test_canonical_acceptance_fixture_is_deterministic_and_covers_outputs():
    events = raw_fixture()
    first = RawBybitReplayHarness(events).run(acceptance_pipeline())
    second = RawBybitReplayHarness(events).run(acceptance_pipeline())
    assert first.to_dict() == second.to_dict()
    context = first.pipeline_result.context
    assert all(getattr(context, name) is not None for name in (
        "structure", "mtf", "liquidity", "orderflow", "value", "fvg",
        "order_blocks", "aggression", "absorption", "effort", "setup", "entry",
    ))
    assert context.event_time == events[-1].event_time
    assert first.pipeline_result.intent is None or first.pipeline_result.intent.paper_only


def test_future_favorable_event_cannot_change_historical_decision():
    baseline = RawBybitReplayHarness(raw_fixture()).run_steps(acceptance_pipeline())[-1].to_dict()
    future = raw_fixture() + [
        raw_fixture()[-1].__class__(100, 100, {
            "topic": "publicTrade.BTCUSDT", "ts": 100000,
            "data": [{"i": "future", "T": 100000, "p": 1000, "v": 1000, "S": "Buy"}],
        })
    ]
    historical = [step for step in RawBybitReplayHarness(future).run_steps(acceptance_pipeline()) if step.pipeline_result.context.event_time == 21][-1]
    assert historical.to_dict() == baseline


def test_forming_candle_and_bad_quality_fail_closed():
    events = raw_fixture()
    forming = events[2].__class__(events[2].event_time, events[2].received_time, {
        "topic": "kline.1.BTCUSDT", "ts": 2000,
        "data": [{"start": 2000, "open": 100, "high": 120, "low": 90, "close": 119, "volume": 100, "confirm": False}],
    })
    result = RawBybitReplayHarness(events[:2] + [forming] + events[3:]).run(acceptance_pipeline())
    assert result.pipeline_result.context.candles
    assert all(candle.confirmed for candle in result.pipeline_result.context.candles)
    assert DataQualityEngine().validate_event({"event_time": 2, "price": 0, "quantity": -1}).status == "INVALID"
    assert ApexBrainPipeline().run(replace(result.pipeline_result.context, data_quality=DataQuality("DATA_INVALID"))).decision.action == "WAIT"


def test_symbol_isolation_and_order_block_cutoff_are_enforced():
    candles = [
        {"event_time": 1, "symbol": "BTCUSDT", "open": 100, "high": 102, "low": 98, "close": 99, "confirmed": True},
        {"event_time": 2, "symbol": "BTCUSDT", "open": 99, "high": 106, "low": 98, "close": 105, "confirmed": True},
        {"event_time": 3, "symbol": "ETHUSDT", "open": 105, "high": 110, "low": 104, "close": 109, "confirmed": True},
    ]
    result = OrderBlockEngine().analyze(candles, as_of=2, symbol="BTCUSDT")
    assert len(result.blocks) == 1
    assert result.blocks[0].symbol == "BTCUSDT"
    assert result.blocks[0].creation_time <= 2


def test_risk_gate_is_authoritative_for_paper_intent():
    result = RawBybitReplayHarness(raw_fixture()).run(acceptance_pipeline()).pipeline_result
    rejected = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20))).run(result.context, daily_drawdown_pct=100)
    assert rejected.decision.action == "WAIT"
    assert rejected.intent is None


def test_paper_engine_requires_approval_and_supports_trailing():
    result = RawBybitReplayHarness(raw_fixture()).run(acceptance_pipeline()).pipeline_result
    if result.intent is None or not result.intent.approved:
        pytest.skip("fixture did not produce an approved intent")
    engine = PaperExecutionEngine(fee_rate=0.001, slippage_rate=0.001)
    position = engine.open(result.intent)
    assert engine.trail(position.stop_loss + 0.01).stop_loss > position.stop_loss
    with pytest.raises(ValueError):
        engine.open(result.intent)