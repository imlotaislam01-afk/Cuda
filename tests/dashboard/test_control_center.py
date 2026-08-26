from types import SimpleNamespace

from brain.dashboard import ControlCenter
from brain.decision import BrainDecision, DecisionLevels
from brain.risk import RiskResult


def test_control_center_projects_canonical_state_without_reanalysis():
    result = SimpleNamespace(
        context=SimpleNamespace(
            symbol="BTCUSDT", current_price=100, structure={"trend": "BULLISH"},
            mtf=None, liquidity=None, orderflow=None, aggression=None, absorption=None,
            value=None, oi=None, funding=0.001, effort=None, regime="TRENDING",
            market_regime="TRENDING", setup=None, entry=None, event_time=10,
        ),
        decision=BrainDecision("WAIT", 0, DecisionLevels(), ["WAIT"], ["MISSING"]),
        risk=RiskResult(False, 0, 0, 0),
    )
    snapshot = ControlCenter().snapshot(result)
    assert snapshot["symbol"] == "BTCUSDT"
    assert snapshot["structure"] == {"trend": "BULLISH"}
    assert snapshot["decision"]["action"] == "WAIT"
    assert snapshot["risk"]["approved"] is False
    assert snapshot["event_time"] == 10
