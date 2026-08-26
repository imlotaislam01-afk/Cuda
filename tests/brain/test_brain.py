from brain.context.market_state import MarketState
from brain.decision import DecisionEngine
from brain.llm import SafeMockLLMProvider
from brain.reasoning import ApexReasoner
from brain.risk import RiskGate


def bullish_market():
    state = MarketState(
        symbol="BTCUSDT",
        timestamp=1,
        price=100000.0,
        timeframe="1m",
        regime="bullish",
        structure={"bias": "bullish"},
        liquidity={"sweep": "sell_side"},
        order_flow={"bias": "bullish"},
        open_interest={"change_pct": 5.2},
        volume={"rvol": 3.4},
    )

    return state


def test_market_state_serialization():
    state = bullish_market()

    data = state.to_dict()

    assert data["symbol"] == "BTCUSDT"
    assert data["price"] == 100000.0
    assert data["structure"]["bias"] == "bullish"


def test_bullish_reasoning():
    state = bullish_market()

    result = ApexReasoner().evaluate(
        state.to_dict()
    )

    assert result.bias == "LONG"
    assert result.confidence >= 75
    assert result.setup_valid is True


def test_wait_when_confluence_is_insufficient():
    state = MarketState(
        symbol="BTCUSDT",
        timestamp=1,
        price=100000.0,
    )

    result = ApexReasoner().evaluate(
        state.to_dict()
    )

    assert result.bias == "WAIT"
    assert result.setup_valid is False


def test_decision_engine_creates_long():
    state = bullish_market()

    reasoning = ApexReasoner().evaluate(
        state.to_dict()
    )

    decision = DecisionEngine().build(
        state.to_dict(),
        reasoning,
    )

    assert decision.action == "LONG"
    assert decision.entry == 100000.0
    assert decision.stop_loss is not None
    assert len(decision.take_profit) == 3
    assert decision.execute is False


def test_risk_gate_approves_valid_trade():
    state = bullish_market()

    reasoning = ApexReasoner().evaluate(
        state.to_dict()
    )

    decision = DecisionEngine().build(
        state.to_dict(),
        reasoning,
    )

    risk = RiskGate().evaluate(
        decision,
        current_positions=0,
        daily_drawdown_pct=0,
        requested_leverage=5,
    )

    assert risk.approved is True


def test_risk_gate_rejects_excessive_leverage():
    state = bullish_market()

    reasoning = ApexReasoner().evaluate(
        state.to_dict()
    )

    decision = DecisionEngine().build(
        state.to_dict(),
        reasoning,
    )

    risk = RiskGate().evaluate(
        decision,
        current_positions=0,
        daily_drawdown_pct=0,
        requested_leverage=20,
    )

    assert risk.approved is False


def test_kill_switch_rejects_trade():
    state = bullish_market()

    reasoning = ApexReasoner().evaluate(
        state.to_dict()
    )

    decision = DecisionEngine().build(
        state.to_dict(),
        reasoning,
    )

    risk_gate = RiskGate()

    risk_gate.kill()

    risk = risk_gate.evaluate(
        decision,
        current_positions=0,
        daily_drawdown_pct=0,
        requested_leverage=5,
    )

    assert risk.approved is False


def test_drawdown_kills_system():
    state = bullish_market()

    reasoning = ApexReasoner().evaluate(
        state.to_dict()
    )

    decision = DecisionEngine().build(
        state.to_dict(),
        reasoning,
    )

    risk_gate = RiskGate()

    risk = risk_gate.evaluate(
        decision,
        current_positions=0,
        daily_drawdown_pct=3.0,
        requested_leverage=5,
    )

    assert risk.approved is False

    # Once killed, another trade must also be rejected.
    risk2 = risk_gate.evaluate(
        decision,
        current_positions=0,
        daily_drawdown_pct=0,
        requested_leverage=1,
    )

    assert risk2.approved is False


def test_position_limit():
    state = bullish_market()

    reasoning = ApexReasoner().evaluate(
        state.to_dict()
    )

    decision = DecisionEngine().build(
        state.to_dict(),
        reasoning,
    )

    risk = RiskGate().evaluate(
        decision,
        current_positions=2,
        daily_drawdown_pct=0,
        requested_leverage=5,
    )

    assert risk.approved is False


def test_llm_is_advisory_only():
    state = bullish_market()

    provider = SafeMockLLMProvider()

    result = provider.analyze(
        state.to_dict(),
        {"test": True},
    )

    assert result["advisory"] is True
    assert result["bias"] == "NEUTRAL"


def test_live_execution_is_not_available():
    from brain.execution import (
        ExecutionEngine,
        LiveExecutionDisabled,
    )

    engine = ExecutionEngine()

    try:
        engine.execute_live()
        assert False, "Live execution should be disabled"
    except LiveExecutionDisabled:
        assert True
