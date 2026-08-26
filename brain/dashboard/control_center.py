from __future__ import annotations

from typing import Any
import asyncio
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websockets


class ControlCenter:
    """Read-only dashboard/API projection of canonical APEX state."""

    def snapshot(self, pipeline_result, paper_position=None, execution_state=None) -> dict[str, Any]:
        context = pipeline_result.context
        decision = pipeline_result.decision
        risk = pipeline_result.risk
        return {
            "symbol": context.symbol,
            "price": context.current_price,
            "structure": self._serialize(context.structure),
            "mtf": self._serialize(context.mtf),
            "liquidity": self._serialize(context.liquidity),
            "orderflow": self._serialize(context.orderflow),
            "aggression": self._serialize(context.aggression),
            "absorption": self._serialize(context.absorption),
            "value": self._serialize(context.value),
            "oi": self._serialize(context.oi),
            "fvg": self._serialize(getattr(context, "fvg", None)),
            "order_blocks": self._serialize(getattr(context, "order_blocks", None)),
            "funding": context.funding,
            "effort": self._serialize(context.effort),
            "regime": context.market_regime,
            "setup": self._serialize(context.setup),
            "entry": self._serialize(context.entry),
            "decision": decision.to_dict(),
            "risk": risk.to_dict(),
            "paper_position": self._serialize(paper_position),
            "reason_codes": list(decision.reasons) + list(decision.invalidation),
            "event_time": context.event_time,
            "observability": self._serialize(getattr(context, "observability", None)),
            "data_quality": self._serialize(getattr(context, "data_quality", None)),
            "feed": getattr(context, "metadata", {}).get("feed_continuity", "UNKNOWN"),
            "execution": self._serialize(execution_state),
        }

    @staticmethod
    def _serialize(value):
        if value is None:
            return None
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, dict):
            return dict(value)
        return vars(value)


class DashboardService:
    """Read-only API facade backed by one canonical pipeline result provider."""

    _routes = {
        "/market": "snapshot",
        "/snapshot": "snapshot",
        "/decision": "decision",
        "/risk": "risk",
        "/paper-position": "paper_position",
        "/position": "paper_position",
        "/observability": "observability",
        "/data-quality": "data_quality",
        "/feed": "feed",
    }

    def __init__(self, result_provider, paper_position_provider=None, execution_state_provider=None) -> None:
        self.result_provider = result_provider
        self.paper_position_provider = paper_position_provider
        self.execution_state_provider = execution_state_provider
        self.control_center = ControlCenter()

    def get(self, path: str) -> dict[str, Any]:
        if path == "/health":
            return {"status": "ok", "read_only": True}
        if path not in self._routes:
            if path.rstrip("/") in {"/order", "/orders", "/trade", "/execute", "/cancel", "/position", "/create_order", "/place_order", "/submit_order", "/cancel_order"}:
                raise PermissionError("Live order endpoints are disabled")
            raise KeyError(path)
        result = self.result_provider()
        if result is None:
            return {"status": "unavailable"}
        snapshot = self.control_center.snapshot(
            result,
            self.paper_position_provider() if self.paper_position_provider else None,
            self.execution_state_provider() if self.execution_state_provider else None,
        )
        key = self._routes[path]
        if key == "data_quality":
            return {key: snapshot.get("data_quality", snapshot.get("observability"))}
        if key == "feed":
            return {key: {"event_time": snapshot.get("event_time"), "symbol": snapshot.get("symbol")}}
        return snapshot if key == "snapshot" else {key: snapshot[key]}


class DashboardHTTPServer(ThreadingHTTPServer):
    def __init__(self, address, service: DashboardService, token: str):
        if not token:
            raise ValueError("Dashboard token is required for network access")
        self.service = service
        self.token = token

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                if not _authorized(handler.headers.get("Authorization"), token):
                    handler.send_response(401)
                    handler.send_header("Content-Length", "0")
                    handler.end_headers()
                    return
                try:
                    payload = service.get(handler.path)
                    body = json.dumps(payload, sort_keys=True, default=str).encode()
                    handler.send_response(200)
                except PermissionError as error:
                    body = json.dumps({"error": "forbidden", "message": str(error)}, sort_keys=True).encode()
                    handler.send_response(403)
                except KeyError:
                    body = b'{"error":"not found"}'
                    handler.send_response(404)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)

            def do_POST(handler):
                handler.send_response(403)
                handler.send_header("Content-Length", "0")
                handler.end_headers()

            def log_message(handler, *_args):
                return

        super().__init__(address, Handler)


class DashboardWebSocket:
    """Read-only async update stream; it never invokes pipeline or execution code."""

    def __init__(self, result_provider, paper_position_provider=None):
        self.service = DashboardService(result_provider, paper_position_provider)
        self.connected = False

    async def updates(self, count: int | None = None):
        self.connected = True
        sent = 0
        try:
            while count is None or sent < count:
                yield self.service.get("/snapshot")
                sent += 1
                await asyncio.sleep(0)
        finally:
            self.connected = False

    def receive(self, message: str) -> dict[str, Any]:
        request = json.loads(message)
        if str(request.get("action", "")).lower() in {"order", "execute", "cancel", "trade"}:
            raise PermissionError("Dashboard stream is read-only")
        return self.service.get("/snapshot")


class DashboardWebSocketServer:
    """Network read-only WebSocket projection backed by the HTTP service state."""

    def __init__(self, result_provider, paper_position_provider=None, host="127.0.0.1", port=0, execution_state_provider=None, token: str | None = None):
        if not token:
            raise ValueError("Dashboard token is required for network access")
        self.service = DashboardService(result_provider, paper_position_provider, execution_state_provider)
        self.token = token
        self.host = host
        self.port = port
        self._server = None

    async def _handler(self, connection):
        authorization = connection.request.headers.get("Authorization", "")
        if not _authorized(authorization, self.token):
            await connection.close(code=1008, reason="Dashboard authentication required")
            return
        await connection.send(json.dumps(self.service.get("/snapshot"), sort_keys=True, default=str))
        async for message in connection:
            try:
                request = json.loads(message)
                action = str(request.get("action", request.get("path", ""))).lower()
                if action in {"order", "orders", "trade", "execute", "cancel", "position", "create-order", "place-order", "submit-order", "cancel-order", "/order", "/orders", "/trade", "/execute", "/cancel", "/position"}:
                    await connection.send(json.dumps({"error": "forbidden", "message": "Dashboard stream is read-only"}, sort_keys=True))
                    continue
                await connection.send(json.dumps(self.service.get("/snapshot"), sort_keys=True, default=str))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                await connection.close(code=1003, reason="Malformed read-only request")
                return

    async def start(self):
        self._server = await websockets.serve(self._handler, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def close(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


def create_app(result_provider, paper_position_provider=None, execution_state_provider=None) -> DashboardService:
    """Create the dependency-free read-only control-center service."""
    return DashboardService(result_provider, paper_position_provider, execution_state_provider)


def create_http_server(result_provider, paper_position_provider=None, host="127.0.0.1", port=0, execution_state_provider=None, token: str | None = None):
    return DashboardHTTPServer((host, port), create_app(result_provider, paper_position_provider, execution_state_provider), token)


def create_websocket_server(result_provider, paper_position_provider=None, host="127.0.0.1", port=0, execution_state_provider=None, token: str | None = None):
    return DashboardWebSocketServer(result_provider, paper_position_provider, host, port, execution_state_provider, token)


def _authorized(header: str | None, token: str) -> bool:
    prefix = "Bearer "
    return bool(header and header.startswith(prefix) and hmac.compare_digest(header[len(prefix):], token))
