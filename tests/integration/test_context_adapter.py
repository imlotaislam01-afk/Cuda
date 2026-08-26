from market.bybit.public_ws import BybitMarketData
from market.integration.context_adapter import LiveSnapshotContextAdapter
from market.integration.live_snapshot import LiveMarketSnapshot


def test_live_snapshot_maps_available_data_without_inventing_feeds():
    snapshot = LiveMarketSnapshot("BTCUSDT")
    snapshot.feed.data = BybitMarketData(
        symbol="BTCUSDT",
        price=100.0,
        bids={99.0: 2.0},
        asks={101.0: 3.0},
        trades=[
            {"id": "t1", "timestamp": 1000, "price": 100.0, "quantity": 1.0, "side": "BUY"}
        ],
        last_update=2.0,
        last_event_time=1.0,
        data_quality="OK",
    )
    context = LiveSnapshotContextAdapter(snapshot).build(calculation_time=3.0)

    assert context is not None
    assert context.exchange == "BYBIT"
    assert context.event_time == 1.0
    assert context.received_time == 2.0
    assert context.calculation_time == 3.0
    assert context.bid == 99.0
    assert context.ask == 101.0
    assert context.spread == 2.0
    assert context.delta == 1.0
    assert context.cvd == 1.0
    assert context.oi is None
    assert context.funding is None
    assert context.price.volume is None