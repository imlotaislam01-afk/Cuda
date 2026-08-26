from brain.decision import (
    APEXDecisionBrain,
    BrainDecision,
    DecisionLevels,
)

from brain.execution import (
    ExecutionIntentBuilder,
)

from brain.risk import RiskGate


def test_approved_intent():

    decision = BrainDecision(
        action="LONG",
        confidence=80,
        levels=DecisionLevels(
            entry=100000,
            stop_loss=99500,
            tp1=100500,
            tp2=101000,
            tp3=102000,
        ),
        reasons=["Bullish confluence"],
    )

    risk = RiskGate().evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=99500,
        leverage=5,
    )

    intent = ExecutionIntentBuilder().build(
        symbol="BTCUSDT",
        decision=decision,
        risk=risk,
    )

    assert intent.approved is True
    assert intent.paper_only is True
    assert intent.action == "LONG"
    assert intent.quantity > 0


def test_rejected_risk_cannot_execute():

    decision = BrainDecision(
        action="LONG",
        confidence=80,
        levels=DecisionLevels(
            entry=100000,
            stop_loss=99500,
        ),
    )

    risk = RiskGate().evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=99500,
        leverage=100,
    )

    intent = ExecutionIntentBuilder().build(
        symbol="BTCUSDT",
        decision=decision,
        risk=risk,
    )

    assert intent.approved is False
    assert intent.paper_only is True


def test_intent_serialization():

    decision = BrainDecision(
        action="LONG",
        confidence=80,
        levels=DecisionLevels(
            entry=100000,
            stop_loss=99500,
        ),
    )

    risk = RiskGate().evaluate(
        action="LONG",
        confidence=80,
        entry=100000,
        stop_loss=99500,
        leverage=5,
    )

    intent = ExecutionIntentBuilder().build(
        symbol="BTCUSDT",
        decision=decision,
        risk=risk,
    )

    data = intent.to_dict()

    assert data["symbol"] == "BTCUSDT"
    assert data["action"] == "LONG"
    assert data["paper_only"] is True
    assert data["metadata"]["live_execution"] is False


def test_decision_brain_still_rejects_wait():

    decision = APEXDecisionBrain().analyze(
        type(
            "Context",
            (),
            {
                "bias": "WAIT",
                "score": 90,
                "current_price": 100000,
            },
        )()
    )

    assert decision.action == "WAIT"
    assert decision.is_trade is False
