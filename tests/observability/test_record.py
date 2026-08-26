from types import SimpleNamespace

from brain.decision import BrainDecision, DecisionLevels
from brain.observability import ObservabilityRecorder
from brain.risk import RiskResult


def test_observability_records_final_decision_and_evidence():
    result = SimpleNamespace(
        context=SimpleNamespace(
            symbol="BTCUSDT", event_time=10, market_regime="TRENDING",
            setup=SimpleNamespace(setup_type="TEST"), structure=object(), mtf=object(),
            liquidity=object(), orderflow=object(), value=object(), effort=object(),
        ),
        decision=BrainDecision("WAIT", 0, DecisionLevels(), ["REGIME_CHOP"], ["NO_SETUP"]),
        risk=RiskResult(False, 0, 0, 0),
    )
    record = ObservabilityRecorder().record(result)
    assert record.symbol == "BTCUSDT"
    assert record.event_time == 10


    def test_observability_does_not_change_pipeline_result():
        from dataclasses import replace
        from types import SimpleNamespace

        from brain.context import MarketContextBuilder
        from brain.pipeline import ApexBrainPipeline

        context = MarketContextBuilder("BTCUSDT", 100).set_event_times(10, 10).set_data_quality("DATA_INCOMPLETE").build(allow_incomplete=True)
        with_observability = ApexBrainPipeline().run(context)
        without_observability_pipeline = ApexBrainPipeline()
        without_observability_pipeline.observability = SimpleNamespace(record=lambda result: None)
        without_observability = without_observability_pipeline.run(context)
        assert with_observability.decision.to_dict() == without_observability.decision.to_dict()
        assert with_observability.risk.to_dict() == without_observability.risk.to_dict()
        assert (with_observability.intent.to_dict() if with_observability.intent else None) == (without_observability.intent.to_dict() if without_observability.intent else None)
    assert record.setup_type == "TEST"
    assert record.reason_codes == ("REGIME_CHOP",)
    assert record.rejected_reason == ("NO_SETUP",)
    assert record.evidence["effort"] is True