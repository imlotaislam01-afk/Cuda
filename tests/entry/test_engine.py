from types import SimpleNamespace

from brain.entry import EntryEngine


def test_entry_engine_returns_precise_valid_levels():
    setup = SimpleNamespace(
        is_setup=True, direction="LONG", entry=100.0, stop=98.0,
        targets=(103.0, 106.0), invalidation="sweep fails", confidence=82.0,
        setup_type="LIQUIDITY_SWEEP_REVERSAL",
    )
    result = EntryEngine().analyze(setup)
    assert result.valid is True
    assert result.risk_reward == 1.5
    assert result.tp2 == 106.0


def test_entry_engine_fails_closed_on_invalid_levels():
    setup = SimpleNamespace(
        is_setup=True, direction="SHORT", entry=100.0, stop=99.0,
        targets=(101.0,), invalidation=None, confidence=80.0,
        setup_type="BREAKOUT_CONTINUATION",
    )
    result = EntryEngine().analyze(setup)
    assert result.valid is False
    assert result.direction == "WAIT"
    assert result.reason_codes == ("INVALID_STOP",)
