from types import SimpleNamespace
from threading import Thread
from urllib.request import urlopen

import pytest

from brain.dashboard import DashboardWebSocket, create_app, create_http_server, create_websocket_server
from brain.decision import BrainDecision, DecisionLevels
from brain.risk import RiskResult


def result():
    context = SimpleNamespace(
        symbol="BTCUSDT", current_price=100, structure=None, mtf=None, liquidity=None,
        orderflow=None, aggression=None, absorption=None, value=None, oi=None,
        funding=0.001, effort=None, market_regime="TRENDING", setup=None, entry=None,
        fvg=None, order_blocks=None, observability=None, event_time=10,
    )
    return SimpleNamespace(context=context, decision=BrainDecision("WAIT", 0, DecisionLevels(), ["WAIT"], ["MISSING"]), risk=RiskResult(False, 0, 0, 0))


def test_dashboard_service_exposes_canonical_read_only_routes():
    app = create_app(lambda: result(), execution_state_provider=lambda: {"mode": "PAPER", "healthy": True})
    assert app.get("/health")["read_only"] is True
    assert app.get("/snapshot")["symbol"] == "BTCUSDT"
    assert app.get("/decision")["decision"]["action"] == "WAIT"
    assert app.get("/risk")["risk"]["approved"] is False
    assert app.get("/observability")["observability"] is None
    assert app.get("/snapshot")["execution"] == {"mode": "PAPER", "healthy": True}


def test_dashboard_service_rejects_order_mutation_routes():
    app = create_app(lambda: result())
    with pytest.raises(PermissionError):
        app.get("/create_order")
    with pytest.raises(PermissionError):
        app.get("/cancel_order")


def test_http_control_center_is_read_only():
    server = create_http_server(lambda: result(), token="test-token")
    try:
        assert server.service.get("/data-quality")["data_quality"] is None
        assert server.service.get("/feed")["feed"]["event_time"] == 10
    finally:
        server.server_close()


def test_http_server_serves_canonical_snapshot_and_forbids_mutation():
    server = create_http_server(lambda: result(), token="test-token")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = __import__("urllib.request", fromlist=["Request"]).Request(f"http://127.0.0.1:{server.server_port}/health", headers={"Authorization": "Bearer test-token"})
        with urlopen(request) as response:
            assert response.status == 200
        with pytest.raises(Exception) as error:
            urlopen(__import__("urllib.request", fromlist=["Request"]).Request(f"http://127.0.0.1:{server.server_port}/order", headers={"Authorization": "Bearer test-token"}))
        assert getattr(error.value, "code", None) == 403
    finally:
        server.shutdown()
        server.server_close()


def test_network_dashboard_requires_configured_token():
    with pytest.raises(ValueError, match="token"):
        create_http_server(lambda: result())
    with pytest.raises(ValueError, match="token"):
        create_websocket_server(lambda: result())


def test_http_dashboard_rejects_missing_token():
    server = create_http_server(lambda: result(), token="test-token")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(Exception) as error:
            urlopen(f"http://127.0.0.1:{server.server_port}/snapshot")
        assert getattr(error.value, "code", None) == 401
    finally:
        server.shutdown()
        server.server_close()


def test_websocket_stream_emits_canonical_state_and_rejects_mutation():
    stream = DashboardWebSocket(lambda: result())
    updates = __import__("asyncio").run(_one_update(stream))
    assert updates["symbol"] == "BTCUSDT"
    with pytest.raises(PermissionError):
        stream.receive('{"action":"execute"}')


def test_network_websocket_serves_snapshot_and_rejects_mutation():
    import asyncio
    import json
    import websockets

    async def exercise():
        server = await create_websocket_server(lambda: result(), token="test-token").start()
        try:
            async with websockets.connect(f"ws://127.0.0.1:{server.port}", additional_headers={"Authorization": "Bearer test-token"}) as client:
                snapshot = json.loads(await client.recv())
                assert snapshot["symbol"] == "BTCUSDT"
                await client.send('{"action":"place-order"}')
                rejection = json.loads(await client.recv())
                assert rejection == {"error": "forbidden", "message": "Dashboard stream is read-only"}
        finally:
            await server.close()

    asyncio.run(exercise())


async def _one_update(stream):
    async for update in stream.updates(1):
        return update