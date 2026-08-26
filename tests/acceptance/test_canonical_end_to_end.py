import asyncio
import json
from threading import Thread
from urllib.request import urlopen

import websockets

from brain.dashboard import create_http_server, create_websocket_server
from brain.execution import PaperExecutionEngine
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from market.integration.live_snapshot import LiveMarketSnapshot
from tests.integration.test_live_canonical_path import _feed_events


def test_raw_feed_to_paper_execution_and_dashboard_transports():
    pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20)))
    pipeline.decision.minimum_confidence = 20
    snapshot = LiveMarketSnapshot("BTCUSDT")
    for message in _feed_events():
        snapshot.feed._process_message(message, received_time=message["ts"] / 1000)

    result = snapshot.run_pipeline(pipeline, calculation_time=13, as_of=11)
    assert result.intent is not None
    paper = PaperExecutionEngine()
    position = paper.open(result.intent, price=result.context.current_price)
    assert position.status == "OPEN"
    provider = lambda: result
    http_server = create_http_server(provider, lambda: position, token="test-token")

    try:
        thread = Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        from urllib.request import Request
        with urlopen(Request(f"http://127.0.0.1:{http_server.server_port}/snapshot", headers={"Authorization": "Bearer test-token"})) as response:
            http_snapshot = json.load(response)
        assert http_snapshot["symbol"] == result.context.symbol
        assert http_snapshot["paper_position"]["status"] == "OPEN"
    finally:
        http_server.shutdown()
        http_server.server_close()

    async def websocket_projection():
        server = await create_websocket_server(provider, lambda: position, token="test-token").start()
        try:
            async with websockets.connect(f"ws://127.0.0.1:{server.port}", additional_headers={"Authorization": "Bearer test-token"}) as client:
                network_snapshot = json.loads(await client.recv())
                assert network_snapshot["decision"] == result.decision.to_dict()
                assert network_snapshot["paper_position"]["symbol"] == position.symbol
        finally:
            await server.close()

    asyncio.run(websocket_projection())
    assert result.context.observability is not None
    assert result.context.observability.event_time == result.context.event_time
