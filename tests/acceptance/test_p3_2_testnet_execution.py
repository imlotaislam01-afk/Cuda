from brain.dashboard import create_app
from brain.execution import (
    BinanceExecutionAdapter,
    BybitExecutionAdapter,
    ExecutionConfig,
    ExecutionCoordinator,
    ExecutionMode,
    ProtectionManager,
)
from tests.execution.test_p3_foundation import intent


def fake_transport(method, path, params):
    if method == "GET" and "account" in path:
        return {"assets": [{"asset": "USDT", "availableBalance": "100000"}], "available_balance": 100000}
    if method == "GET" and "position" in path:
        return {"positions": [{"symbol": "BTCUSDT", "positionAmt": "1", "entryPrice": "100"}]}
    return {
        "symbol": "BTCUSDT",
        "orderId": "testnet-1",
        "clientOrderId": params.get("newClientOrderId", params.get("clientOrderId", "apex-protection")),
        "side": params.get("side", "BUY"),
        "type": params.get("type", "MARKET"),
        "origQty": str(params.get("quantity", 1)),
        "executedQty": str(params.get("quantity", 1)),
        "avgPrice": "100",
        "status": "FILLED",
        "stopPrice": str(params.get("stopPrice") or 98),
    }


def test_binance_testnet_canonical_path_reaches_fill_protection_reconciliation_dashboard():
    config = ExecutionConfig(mode=ExecutionMode.TESTNET, credentials={"api_key": "fake", "api_secret": "fake"})
    adapter = BinanceExecutionAdapter(config, transport=fake_transport)
    coordinator = ExecutionCoordinator(adapter, config)
    outcome = coordinator.submit_intent(intent(), now=10)
    assert outcome.status == "SUBMITTED"
    assert outcome.order.status.value == "FILLED"
    assert adapter.get_positions()[0].quantity == outcome.order.filled_quantity
    protection = ProtectionManager().create_plan(intent(), exchange="BINANCE", mode=ExecutionMode.TESTNET)[1:]
    protected = [coordinator.submit_order_request(order, now=10).order for order in protection]
    assert protected[0].status.value == "FILLED"
    reconciliation = coordinator.reconcile(adapter.get_positions()[0])
    assert reconciliation.status == "MATCH"
    dashboard = create_app(lambda: type("Result", (), {"context": type("Context", (), {"symbol": "BTCUSDT", "current_price": 100, "structure": None, "mtf": None, "liquidity": None, "orderflow": None, "aggression": None, "absorption": None, "value": None, "oi": None, "funding": 0.0, "effort": None, "market_regime": "UNKNOWN", "setup": None, "entry": None, "fvg": None, "order_blocks": None, "observability": None, "event_time": 10, "metadata": {}})(), "decision": type("Decision", (), {"to_dict": lambda self: {}, "reasons": [], "invalidation": []})(), "risk": type("Risk", (), {"to_dict": lambda self: {}})()})(), execution_state_provider=lambda: {"mode": "TESTNET", "exchange": "BINANCE", "order_status": outcome.order.status.value, "filled_quantity": outcome.order.filled_quantity, "protection_status": "VERIFIED", "reconciliation_status": reconciliation.status})
    assert dashboard.get("/snapshot")["execution"]["exchange"] == "BINANCE"


def test_bybit_testnet_normalization_uses_same_canonical_contract():
    config = ExecutionConfig(mode=ExecutionMode.TESTNET, credentials={"api_key": "fake", "api_secret": "fake"})
    adapter = BybitExecutionAdapter(config, transport=fake_transport)
    outcome = ExecutionCoordinator(adapter, config).submit_intent(intent(), now=10)
    assert outcome.order.exchange == "BYBIT"
    assert outcome.order.status.value == "FILLED"
