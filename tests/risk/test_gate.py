from brain.risk import (
    RiskConfig,
    RiskGate,
)
from math import inf
from brain.context import ExchangeMetadata


def test_risk_approved():

    gate = RiskGate(
        RiskConfig(
            account_size=500,
            risk_per_trade_pct=1,
            max_leverage=5,
            minimum_confidence=75,
        )
    )

    result = gate.evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=99500,
        leverage=5,
    )

    assert result.approved is True
    assert result.risk_usd == 5
    assert result.position_size > 0


def test_missing_stop_rejected():

    result = RiskGate().evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=None,
        leverage=5,
    )

    assert result.approved is False
    assert any(
        "stop" in x.lower()
        for x in result.rejection_reasons
    )


def test_excessive_leverage_rejected():

    result = RiskGate().evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=99500,
        leverage=10,
    )

    assert result.approved is False


def test_drawdown_kill_switch():

    result = RiskGate().evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=99500,
        leverage=5,
        daily_drawdown_pct=3,
    )

    assert result.approved is False


def test_position_limit():

    result = RiskGate().evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=99500,
        leverage=5,
        open_positions=2,
    )

    assert result.approved is False


def test_wrong_long_stop():

    result = RiskGate().evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=101000,
        leverage=5,
    )

    assert result.approved is False


def test_wrong_short_stop():

    result = RiskGate().evaluate(
        action="SHORT",
        confidence=80,
        entry=100000,
        stop_loss=99000,
        leverage=5,
    )

    assert result.approved is False


def test_named_risk_profiles_have_required_thresholds():
    conservative = RiskConfig.conservative()
    aggressive = RiskConfig.aggressive()
    assert (conservative.risk_per_trade_pct, conservative.max_leverage, conservative.max_correlated_positions) == (1.0, 5.0, 1)
    assert (aggressive.risk_per_trade_pct, aggressive.max_leverage, aggressive.max_correlated_positions) == (2.0, 10.0, 2)


def test_correlated_position_limit_is_authoritative():
    gate = RiskGate(RiskConfig.conservative())
    result = gate.evaluate(
        action="LONG", confidence=80, entry=100, stop_loss=99, leverage=5,
        correlated_positions=1,
    )
    assert result.approved is False
    assert any("Correlated" in reason for reason in result.rejection_reasons)


def test_minimum_quantity_failure_cannot_remain_approved():
    result = RiskGate(RiskConfig(account_size=1, minimum_confidence=0)).evaluate(
        action="LONG", confidence=80, entry=100, stop_loss=99, leverage=1,
        exchange_metadata=ExchangeMetadata("BTCUSDT", 0.1, 1.0, 1.0),
    )
    assert result.approved is False
    assert result.position_size == 0


def test_non_finite_correlated_position_count_is_rejected():
    result = RiskGate().evaluate(
        action="LONG", confidence=80, entry=100, stop_loss=99, leverage=1,
        correlated_positions=inf,
    )
    assert result.approved is False
