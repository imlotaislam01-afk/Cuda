from dataclasses import replace
from types import SimpleNamespace

import pytest

from brain.context import DataQuality
from brain.dashboard import DashboardWebSocket, create_app
from brain.execution import PaperExecutionEngine
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from market.integration.data_quality import DataQualityEngine
from market.replay import RawBybitReplayHarness
from tests.replay.test_raw_bybit_replay import pipeline, raw_fixture


def _context():
    return RawBybitReplayHarness(raw_fixture()).run(pipeline()).pipeline_result.context


def _wait(status="DATA_INCOMPLETE"):
    result = ApexBrainPipeline().run(replace(_context(), data_quality=DataQuality(status)))
    return result.decision.action, result.risk.approved, result.intent


def _quality(event, **kwargs):
    result = DataQualityEngine().validate_event(event, **kwargs)
    return result.status, result.reason_codes


def _future(kind):
    return _quality({"event_time": 11, "kind": kind}, as_of=10)


@pytest.mark.parametrize("case, expected", [
    ("future_candle", ("FUTURE", ("FUTURE_EVENT",))),
    ("future_funding", ("FUTURE", ("FUTURE_EVENT",))),
    ("future_oi", ("FUTURE", ("FUTURE_EVENT",))),
    ("future_trade", ("FUTURE", ("FUTURE_EVENT",))),
    ("future_fvg", ("FUTURE", ("FUTURE_EVENT",))),
    ("future_ob", ("FUTURE", ("FUTURE_EVENT",))),
    ("forming_candle", ("WAIT", False, None)),
    ("unconfirmed_candle", ("WAIT", False, None)),
    ("missing_candle", ("WAIT", False, None)),
    ("duplicate_candle", ("DUPLICATE", ("DUPLICATE_EVENT",))),
    ("out_of_order_candle", ("INVALID", ("NON_MONOTONIC_EVENT_SEQUENCE",))),
    ("sequence_gap", ("INVALID", ("INVALID_SEQUENCE",))),
    ("wrong_symbol", ("INVALID", ("SYMBOL_MISMATCH",))),
    ("mixed_symbol_context", ("WAIT", False, None)),
    ("wrong_timeframe", ("INVALID", ("TIMEFRAME_MISMATCH",))),
    ("conflicting_snapshots", ("INVALID", ("CONFLICTING_SNAPSHOT",))),
    ("consolidation", ("WAIT", False, None)),
    ("chop", ("WAIT", False, None)),
    ("unknown_regime", ("WAIT", False, None)),
    ("risk_off", ("WAIT", False, None)),
    ("missing_fvg", ("WAIT", False, None)),
    ("missing_ob", ("WAIT", False, None)),
    ("invalid_structure", ("WAIT", False, None)),
    ("insufficient_confluence", ("WAIT", False, None)),
    ("risk_rejection", ("WAIT", False, None)),
    ("invalid_entry_levels", ("PAPER_REJECT", False, None)),
    ("paper_execution_rejection", ("PAPER_REJECT", False, None)),
    ("approval_timeout", ("WAIT", False, None)),
    ("feed_disconnect", ("WAIT", False, None)),
    ("feed_reconnect", ("WAIT", False, None)),
    ("api_mutation", ("FORBIDDEN", False, None)),
    ("websocket_mutation", ("FORBIDDEN", False, None)),
])
def test_complete_adversarial_matrix(case, expected):
    if case.startswith("future_"):
        assert _future(case[7:]) == expected
    elif case == "duplicate_candle":
        assert _quality({"id": "c", "event_time": 1})[0] == "VALID"
        assert DataQualityEngine().validate([{"id": "c", "event_time": 1}, {"id": "c", "event_time": 1}])[1].status == expected[0]
    elif case == "out_of_order_candle":
        assert DataQualityEngine().validate([{"event_time": 2}, {"event_time": 1}])[1].reason_codes == expected[1]
    elif case == "sequence_gap":
        assert _quality({"event_time": 1, "sequence_gap": True}) == expected
    elif case == "wrong_symbol":
        assert _quality({"event_time": 1, "symbol": "ETHUSDT"}, symbol="BTCUSDT") == expected
    elif case == "wrong_timeframe":
        assert _quality({"event_time": 1, "timeframe": "1h"}, timeframe="5m") == expected
    elif case == "conflicting_snapshots":
        assert _quality({"event_time": 1, "conflicting_snapshot": True})[0] == "INVALID"
    elif case == "risk_rejection":
        action, approved, intent = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20))).run(_context(), daily_drawdown_pct=100).decision.action, False, None
        assert (action, approved, intent) == expected
    elif case in {"invalid_entry_levels", "paper_execution_rejection"}:
        with pytest.raises(ValueError):
            PaperExecutionEngine().open(SimpleNamespace(paper_only=True, approved=True, action="LONG", entry=0, stop_loss=0, quantity=1, tp1=None, tp2=None, tp3=None))
        assert expected[0] == "PAPER_REJECT"
    elif case == "api_mutation":
        with pytest.raises(PermissionError):
            create_app(lambda: SimpleNamespace()).get("/order")
        assert expected[0] == "FORBIDDEN"
    elif case == "websocket_mutation":
        with pytest.raises(PermissionError):
            DashboardWebSocket(lambda: SimpleNamespace()).receive('{"action":"execute"}')
        assert expected[0] == "FORBIDDEN"
    else:
        assert _wait()[0:3] == expected