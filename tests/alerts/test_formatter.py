from types import SimpleNamespace

from brain.alerts import AlertFormatter
from brain.decision import BrainDecision, DecisionLevels
from brain.risk import RiskResult


def result(action="LONG", approved=True):
    decision = BrainDecision(action, 80, DecisionLevels(100, 98, 103, 106), ["confirmed"], [], {"setup_type": "TEST"})
    context = SimpleNamespace(
        symbol="BTCUSDT", setup=SimpleNamespace(setup_type="TEST"), structure=object(), mtf=object(),
        liquidity=object(), orderflow=object(), value=object(), effort=object(), market_regime="TRENDING",
    )
    intent = SimpleNamespace(approved=approved) if approved else None
    risk = RiskResult(approved, 5, 2.5, 5)
    return SimpleNamespace(context=context, decision=decision, intent=intent, risk=risk)


def test_alert_formats_accepted_paper_signal():
    alert = AlertFormatter().format(result())
    assert alert.state == "ACCEPT"
    assert alert.paper_only is True
    assert "MODE: PAPER_ONLY" in alert.text
    assert "ENTRY: 100" in alert.text


def test_alert_formats_rejection_without_live_claim():
    alert = AlertFormatter().format(result(action="WAIT", approved=False))
    assert alert.state == "WAIT"
    assert "REJECTED:" in alert.text
    assert "MODE: PAPER_ONLY" in alert.text
