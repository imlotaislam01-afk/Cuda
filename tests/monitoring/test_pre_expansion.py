from types import SimpleNamespace

from brain.monitoring import PreExpansionDetector


def context(**kwargs):
    defaults = dict(
        data_quality_status="OK", event_time=10, oi_change=3.0,
        rvol=SimpleNamespace(rvol=2.0),
        market_regime="COMPRESSION",
        aggression=SimpleNamespace(direction="BULLISH"),
        liquidity=SimpleNamespace(latest_sweep=None),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_pre_expansion_is_research_only_and_deterministic():
    detector = PreExpansionDetector()
    first = detector.analyze(context(), as_of=10)
    second = detector.analyze(context(), as_of=10)
    assert first.state == "BREAKOUT_IMMINENT"
    assert first.to_dict() == second.to_dict()
    assert not hasattr(first, "decision")


def test_liquidity_event_has_priority_without_trade_decision():
    result = PreExpansionDetector().analyze(
        context(liquidity=SimpleNamespace(latest_sweep=object())), as_of=10
    )
    assert result.state == "LIQUIDITY_EVENT"


def test_bad_data_fails_closed_to_risk_off():
    result = PreExpansionDetector().analyze(context(data_quality_status="DATA_STALE"), as_of=10)
    assert result.state == "RISK_OFF"
    assert result.score == 0.0
