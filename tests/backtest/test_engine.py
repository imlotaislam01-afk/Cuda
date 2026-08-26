from types import SimpleNamespace

from market.backtest import BacktestEngine


def decision(action, entry=100.0, stop=98.0, target=103.0, setup="TEST"):
    return SimpleNamespace(
        action=action, is_trade=action in {"LONG", "SHORT"}, entry=entry, stop_loss=stop,
        levels=SimpleNamespace(tp1=target), setup_type=setup,
    )


def test_backtest_reports_core_metrics_and_breakdowns():
    result = BacktestEngine().run([
        {"decision": decision("LONG"), "final_price": 103, "hold_time": 5, "regime": "TRENDING"},
        {"decision": decision("LONG"), "final_price": 98, "hold_time": 7, "regime": "CHOP"},
    ])
    assert result.total_trades == 2
    assert result.wins == 1
    assert result.losses == 1
    assert result.win_rate == 0.5
    assert result.profit_factor == 1.5
    assert result.setup_performance["TEST"]["trades"] == 2
    assert result.regime_performance["CHOP"]["wins"] == 0


def test_backtest_is_deterministic_and_ignores_waits():
    records = [{"decision": decision("WAIT"), "final_price": 200}]
    first = BacktestEngine().run(records)
    second = BacktestEngine().run(records)
    assert first.to_dict() == second.to_dict()
    assert first.total_trades == 0
