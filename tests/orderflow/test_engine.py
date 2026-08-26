from market.orderflow import OrderFlowEngine


def make_trade(trade_id, timestamp, side, quantity):
    return {
        "id": trade_id,
        "timestamp": timestamp,
        "side": side,
        "quantity": quantity,
    }


def test_duplicate_trade_is_counted_once():
    engine = OrderFlowEngine()
    item = make_trade("1", 1, "BUY", 2)

    result = engine.analyze([item, item])

    assert result.buy_volume == 2
    assert result.delta == 2
    assert result.cumulative_delta == 2


def test_replay_is_deterministic():
    sequence = [
        make_trade("1", 1, "BUY", 2),
        make_trade("2", 2, "SELL", 1),
    ]

    first = OrderFlowEngine().analyze(sequence)
    replayed = OrderFlowEngine().analyze(sequence + sequence)

    assert replayed == first


def test_out_of_order_trades_have_deterministic_cvd():
    ordered = [
        make_trade("1", 1, "BUY", 2),
        make_trade("2", 2, "SELL", 1),
    ]

    first = OrderFlowEngine().analyze(ordered)
    second = OrderFlowEngine().analyze(list(reversed(ordered)))

    assert second.cumulative_delta == first.cumulative_delta
    assert second.buy_volume == 2
    assert second.sell_volume == 1


def test_cutoff_excludes_future_trades_from_all_flow_totals():
    engine = OrderFlowEngine()
    trades = [
        make_trade("1", 100, "BUY", 2),
        make_trade("2", 200, "SELL", 1),
        make_trade("3", 300, "SELL", 10),
    ]

    result = engine.analyze(trades, as_of=200)

    assert result.buy_volume == 2
    assert result.sell_volume == 1
    assert result.delta == 1
    assert result.cumulative_delta == 1
    assert result.trade_count == 2
    assert result.buy_sell_imbalance == 1 / 3


def test_cutoff_result_is_unchanged_by_future_events_and_symbols_are_isolated():
    engine = OrderFlowEngine()
    visible = [make_trade("same-id", 100, "BUY", 2)]
    future = make_trade("future", 300, "SELL", 8)
    other_symbol = {**make_trade("same-id", 100, "SELL", 20), "symbol": "ETHUSDT"}

    first = engine.analyze(visible, as_of=200, symbol="BTCUSDT")
    second = engine.analyze(visible + [future, other_symbol], as_of=200, symbol="BTCUSDT")

    assert second == first
    assert second.trade_count == 1