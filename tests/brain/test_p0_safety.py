import math

import pytest

from brain.decision import APEXDecisionBrain
from brain.risk import RiskConfig, RiskGate


def test_decision_blocks_invalid_data_quality():
    class Context:
        bias = "LONG"
        score = 100
        current_price = 100
        data_quality = "DATA_STALE"

    assert APEXDecisionBrain().analyze(Context()).action == "WAIT"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_risk_rejects_non_finite_values(value):
    result = RiskGate().evaluate(
        action="LONG",
        confidence=value,
        entry=100,
        stop_loss=99,
        leverage=1,
    )
    assert result.approved is False
    assert any("finite" in reason for reason in result.rejection_reasons)


def test_kill_switch_reset_requires_audited_confirmation():
    gate = RiskGate()
    gate.kill()

    with pytest.raises(ValueError):
        gate.reset()

    gate.reset(confirm=True, reason="Operator reviewed daily loss")
    assert gate.killed is False
    assert [item["state"] for item in gate.audit_log] == ["KILLED", "RESET"]


def test_risk_sizing_accounts_for_costs_and_quantity_step():
    gate = RiskGate(
        config=RiskConfig(
            fee_rate_pct=0.1,
            slippage_pct=0.1,
            quantity_step=0.1,
        )
    )
    result = gate.evaluate(
        action="LONG",
        confidence=80,
        entry=100,
        stop_loss=99,
        leverage=1,
    )
    assert result.approved is True
    assert result.position_size < 5
    assert round(result.position_size, 1) == result.position_size