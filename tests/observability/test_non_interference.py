from copy import deepcopy
from types import SimpleNamespace

from brain.execution import PaperExecutionEngine
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from market.integration.live_snapshot import LiveMarketSnapshot
from tests.integration.test_live_canonical_path import _feed_events


def _run_pipeline(observability_enabled):
    pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20)))
    pipeline.decision.minimum_confidence = 20
    if not observability_enabled:
        pipeline.observability = SimpleNamespace(record=lambda result: None)
    snapshot = LiveMarketSnapshot("BTCUSDT")
    for message in _feed_events():
        snapshot.feed._process_message(message, received_time=message["ts"] / 1000)
    result = snapshot.run_pipeline(pipeline, calculation_time=13, as_of=11)
    position = None
    if result.intent is not None:
        position = PaperExecutionEngine().open(result.intent, price=result.context.current_price)
    return result, position


def _decision_state(result):
    serialized = deepcopy(result.to_dict())
    serialized["context"].pop("observability", None)
    return serialized


def test_observability_full_state_equivalence_and_record_presence():
    without, without_position = _run_pipeline(False)
    with_observability, with_position = _run_pipeline(True)

    assert _decision_state(without) == _decision_state(with_observability)
    assert (without_position.to_dict() if without_position else None) == (
        with_position.to_dict() if with_position else None
    )
    assert with_observability.context.observability is not None
    assert with_observability.context.observability.event_time == with_observability.context.event_time


def test_observability_record_does_not_mutate_original_result_inputs():
    result, _ = _run_pipeline(False)
    before = _decision_state(result)
    recorder = ApexBrainPipeline().observability
    record = recorder.record(result)
    assert record.to_dict()["event_time"] == result.context.event_time
    assert _decision_state(result) == before
