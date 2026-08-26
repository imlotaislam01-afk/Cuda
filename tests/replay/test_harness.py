from brain.context import MarketContextBuilder
from brain.pipeline import ApexBrainPipeline
from market.replay import ReplayEvent, ReplayHarness


def make_context(events, event_time):
    return (
        MarketContextBuilder("BTCUSDT", 100)
        .set_event_times(event_time=event_time, calculation_time=event_time)
        .set_data_quality("DATA_INCOMPLETE")
        .build(allow_incomplete=True)
    )


def test_replay_is_deterministic_and_rejects_future_order():
    events = [ReplayEvent(1, "trade", {"id": "a"}), ReplayEvent(2, "trade", {"id": "b"})]
    harness = ReplayHarness(events, make_context)
    first = [result.decision.to_dict() for result in harness.run(ApexBrainPipeline())]
    second = [result.decision.to_dict() for result in harness.run(ApexBrainPipeline())]
    assert first == second


def test_raw_replay_steps_are_incremental_and_deterministic():
    from market.replay import RawBybitEvent, RawBybitReplayHarness

    events = [
        RawBybitEvent(1, 1, {"topic": "tickers.BTCUSDT", "ts": 1000, "data": {"lastPrice": "100", "volume24h": "10000000"}}),
        RawBybitEvent(2, 2, {"topic": "tickers.BTCUSDT", "ts": 2000, "data": {"lastPrice": "101", "volume24h": "10000000"}}),
    ]
    harness = RawBybitReplayHarness(events)
    first = [item.to_dict() for item in harness.run_steps(ApexBrainPipeline())]
    second = [item.to_dict() for item in harness.run_steps(ApexBrainPipeline())]

    assert first == second
    assert len(first) == 2
    assert [item["context"]["event_time"] for item in first] == [1, 2]


def test_raw_replay_cutoff_is_immune_to_future_events():
    from market.replay import RawBybitEvent, RawBybitReplayHarness

    historical = [
        RawBybitEvent(1, 1, {"topic": "tickers.BTCUSDT", "ts": 1000, "data": {"lastPrice": "100"}}),
        RawBybitEvent(2, 2, {"topic": "tickers.BTCUSDT", "ts": 2000, "data": {"lastPrice": "101"}}),
    ]
    future = historical + [
        RawBybitEvent(3, 3, {"topic": "tickers.BTCUSDT", "ts": 3000, "data": {"lastPrice": "999"}}),
    ]
    first = RawBybitReplayHarness(historical).run_steps(ApexBrainPipeline(), as_of=2)
    second = RawBybitReplayHarness(future).run_steps(ApexBrainPipeline(), as_of=2)
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]


def test_raw_replay_classifies_out_of_order_input_without_contaminating_state():
    from market.replay import RawBybitEvent, RawBybitReplayHarness

    events = [
        RawBybitEvent(2, 2, {"topic": "tickers.BTCUSDT", "ts": 2000, "data": {"lastPrice": "101"}}),
        RawBybitEvent(1, 1, {"topic": "tickers.BTCUSDT", "ts": 1000, "data": {"lastPrice": "100"}}),
    ]
    harness = RawBybitReplayHarness(events)
    results = harness.run_steps(ApexBrainPipeline())
    assert [item.pipeline_result.context.event_time for item in results] == [1.0, 2.0]
    assert any(item["status"] == "OUT_OF_ORDER" for item in harness.diagnostics)