from types import SimpleNamespace

from brain.setup import SetupEngine


def context(**overrides):
    structure = SimpleNamespace(bos="BULLISH", trend="BULLISH")
    liquidity = SimpleNamespace(latest_sweep=SimpleNamespace(displacement=True))
    flow = SimpleNamespace(bias="bullish")
    absorption = SimpleNamespace(detected=True)
    base = dict(
        data_quality_status="OK", current_price=100.0, bias="LONG",
        structure=structure, liquidity=liquidity, orderflow=flow,
        absorption=absorption, value=SimpleNamespace(state="BALANCE"),
        mtf=SimpleNamespace(aligned=False, conflict=False), volatility=2.0,
        price=SimpleNamespace(atr=None),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_liquidity_sweep_reversal_requires_complete_evidence():
    result = SetupEngine().analyze(context())
    assert result.setup_type == "LIQUIDITY_SWEEP_REVERSAL"
    assert result.direction == "LONG"
    assert result.entry == 100.0
    assert result.targets == (103.0, 104.0)


def test_setup_fails_closed_for_conflicting_or_missing_evidence():
    conflict = SetupEngine().analyze(context(bias="WAIT"))
    missing = SetupEngine().analyze(context(orderflow=None))
    assert conflict.direction == "WAIT"
    assert missing.direction == "WAIT"
    assert "INSUFFICIENT_SETUP_EVIDENCE" not in missing.reason_codes


def test_setup_classification_is_deterministic():
    engine = SetupEngine()
    first = engine.analyze(context())
    second = engine.analyze(context())
    assert first.to_dict() == second.to_dict()
