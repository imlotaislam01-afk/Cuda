from types import SimpleNamespace

from brain.management import PositionManagementEngine


def test_directional_effort_trails_and_keeps_runner():
    position = SimpleNamespace(action="LONG", entry=100.0, stop_loss=98.0)
    result = PositionManagementEngine().analyze(
        position,
        current_price=104.0,
        effort=SimpleNamespace(effort_state="BULLISH_EFFORT"),
        atr=2.0,
        as_of=10,
    )
    assert result.action == "TRAIL"
    assert result.stop_loss == 102.0
    assert result.runner is True


def test_opposing_absorption_reduces_position():
    position = SimpleNamespace(action="LONG", entry=100.0, stop_loss=98.0)
    result = PositionManagementEngine().analyze(
        position,
        current_price=101.0,
        effort=SimpleNamespace(effort_state="ABSORBED_SELLING"),
    )
    assert result.action == "REDUCE"
    assert result.reason == "OPPOSING_ABSORPTION"


def test_stop_and_invalid_position_fail_closed():
    position = SimpleNamespace(action="LONG", entry=100.0, stop_loss=98.0)
    stopped = PositionManagementEngine().analyze(position, current_price=98.0)
    invalid = PositionManagementEngine().analyze(position, current_price=100.0, as_of=10)
    assert stopped.action == "EXIT"
    assert invalid.action == "HOLD"
