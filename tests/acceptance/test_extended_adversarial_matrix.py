import asyncio
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
import websockets

from brain.dashboard import create_app, create_http_server, create_websocket_server
from brain.execution import PaperExecutionEngine
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from market.integration.data_quality import DataQualityEngine
from tests.dashboard.test_service import result as dashboard_result
from tests.integration.test_live_canonical_path import _feed_events


def test_temporal_and_cutoff_fail_closed_quality_cases():
    engine = DataQualityEngine()
    assert engine.validate_event({"kind": "trade", "event_time": 11}, as_of=10).reason_codes == ("FUTURE_EVENT",)
    assert engine.validate_event({"kind": "trade", "event_time": 1, "stale": True}).reason_codes == ("STALE_EVENT",)
    regression = engine.validate([{"event_time": 2}, {"event_time": 1, "timestamp_regression": True}])
    assert regression[1].reason_codes == ("TIMESTAMP_REGRESSION",)
    assert engine.validate_event({"event_time": 1_700_000_000_000, "timestamp_unit": "seconds"}).reason_codes == ("TIMESTAMP_UNIT_MISMATCH",)
    historical = engine.validate([
        {"kind": "trade", "event_time": 1, "price": 0, "quantity": 1, "side": "BUY"},
        {"kind": "trade", "event_time": 10, "price": 100, "quantity": 1, "side": "BUY"},
    ], as_of=5)
    assert historical[0].status == "INVALID"
    assert historical[1].status == "FUTURE"


def test_continuity_and_identity_cases_are_explicit():
    engine = DataQualityEngine()
    duplicate = engine.validate([{"kind": "trade", "id": "x", "event_time": 1}, {"kind": "trade", "id": "x", "event_time": 1}])
    assert duplicate[1].status == "DUPLICATE"
    assert duplicate[1].reason_codes == ("DUPLICATE_EVENT",)
    assert "INVALID_SEQUENCE" in engine.validate_event({"event_time": 1, "sequence_gap": True}).reason_codes
    assert "SEQUENCE_REGRESSION" in engine.validate_event({"event_time": 1, "sequence_regression": True}).reason_codes
    assert "RECONNECT_REQUIRED" in engine.validate_event({"event_time": 1, "reconnect": True, "reconnect_required": True}).reason_codes
    assert "SYMBOL_MISMATCH" in engine.validate_event({"event_time": 1, "symbol": "ETHUSDT"}, symbol="BTCUSDT").reason_codes
    assert "TIMEFRAME_MISMATCH" in engine.validate_event({"event_time": 1, "timeframe": "5m"}, timeframe="1m").reason_codes
    assert "CONFLICTING_RECORD" in engine.validate_event({"event_time": 1, "conflicting_snapshot": True, "conflicting_record": True}).reason_codes


def test_each_feed_class_rejects_invalid_market_records():
    engine = DataQualityEngine()
    trade = engine.validate_event({"kind": "trade", "event_time": 1, "price": 0, "quantity": 1, "side": "BUY"})
    candle = engine.validate_event({"kind": "candle", "event_time": 1, "open": 10, "high": 9, "low": 8, "close": 9})
    book = engine.validate_event({"kind": "orderbook", "event_time": 1, "bids": [[101, 1]], "asks": [[100, 1]]})
    oi = engine.validate_event({"kind": "oi", "event_time": 1, "value": -1})
    funding = engine.validate_event({"kind": "funding", "event_time": 1, "value": "invalid"})
    assert trade.status == "INVALID" and "INVALID_PRICE" in trade.reason_codes
    assert candle.status == "INVALID" and "INVALID_OHLC" in candle.reason_codes
    assert book.status == "INVALID" and "CROSSED_BOOK" in book.reason_codes
    assert oi.status == "INVALID" and "INVALID_VALUE" in oi.reason_codes
    assert funding.status == "INVALID" and "INVALID_VALUE" in funding.reason_codes


def test_canonical_quality_decision_risk_and_paper_execution_cases():
    pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20)))
    pipeline.decision.minimum_confidence = 20
    snapshot = __import__("market.integration.live_snapshot", fromlist=["LiveMarketSnapshot"]).LiveMarketSnapshot("BTCUSDT")
    for message in _feed_events():
        snapshot.feed._process_message(message, received_time=message["ts"] / 1000)
    result = snapshot.run_pipeline(pipeline, calculation_time=13, as_of=11)
    assert result.intent is not None
    position = PaperExecutionEngine().open(result.intent, price=result.context.current_price)
    assert position.status == "OPEN"
    rejected_pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=101)))
    rejected = rejected_pipeline.run(result.context)
    assert rejected.intent is None
    with pytest.raises(ValueError):
        PaperExecutionEngine().open(result.intent, price=result.intent.stop_loss - 1)


def test_http_matrix_covers_get_mutation_malformed_and_determinism():
    service = create_app(lambda: dashboard_result())
    assert service.get("/snapshot") == service.get("/snapshot")
    assert service.get("/market")["symbol"] == "BTCUSDT"
    with pytest.raises(PermissionError):
        service.get("/execute")
    server = create_http_server(lambda: dashboard_result(), token="test-token")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from urllib.request import Request
        with urlopen(Request(f"http://127.0.0.1:{server.server_port}/snapshot", headers={"Authorization": "Bearer test-token"})) as response:
            assert response.status == 200
        with pytest.raises(HTTPError) as error:
            urlopen(Request(f"http://127.0.0.1:{server.server_port}/order", headers={"Authorization": "Bearer test-token"}))
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_network_websocket_matrix_covers_connection_rejection_and_reconnect():
    async def exercise():
        server = await create_websocket_server(lambda: dashboard_result(), token="test-token").start()
        try:
            async with websockets.connect(f"ws://127.0.0.1:{server.port}", additional_headers={"Authorization": "Bearer test-token"}) as client:
                first = json.loads(await client.recv())
                assert first == json.loads(json.dumps(first, sort_keys=True))
                await client.send('{"action":"execute"}')
                assert json.loads(await client.recv())["error"] == "forbidden"
                await client.send("not-json")
                with pytest.raises(websockets.exceptions.ConnectionClosedError) as error:
                    await asyncio.wait_for(client.recv(), timeout=2)
                assert error.value.code == 1003
            async with websockets.connect(f"ws://127.0.0.1:{server.port}", additional_headers={"Authorization": "Bearer test-token"}) as client:
                second = json.loads(await client.recv())
                assert second == first
        finally:
            await server.close()

    asyncio.run(exercise())
