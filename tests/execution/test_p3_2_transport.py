import json
from urllib.error import HTTPError

import pytest

from brain.execution import (
    AuthenticatedRESTTransport,
    BinanceExecutionAdapter,
    BybitExecutionAdapter,
    ExecutionConfig,
    ExecutionCoordinator,
    ExecutionMode,
    ExecutionTransportError,
    ExchangeMetadataService,
    ExecutionLedger,
    OrderRequest,
    OrderStateMachine,
    OrderStatus,
)
from brain.context import ExchangeMetadata
from tests.execution.test_p3_foundation import intent


def test_binance_transport_signs_testnet_request_without_secret_leak():
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return b'{"assets": []}'

    def opener(request, timeout):
        captured.update(url=request.full_url, headers=dict(request.headers), timeout=timeout)
        return Response()

    transport = AuthenticatedRESTTransport("BINANCE", "key", "secret", "https://testnet.binancefuture.com", opener=opener, clock=lambda: 1.0)
    assert transport.request("GET", "/fapi/v2/account") == {"assets": []}
    assert captured["url"].startswith("https://testnet.binancefuture.com/")
    assert "secret" not in captured["url"]
    assert captured["headers"]["X-mbx-apikey"] == "key"


def test_bybit_transport_signs_json_request_and_rejects_production_endpoint():
    transport = AuthenticatedRESTTransport("BYBIT", "key", "secret", "https://api-testnet.bybit.com", clock=lambda: 1.0)
    assert transport.endpoint.base_url == "https://api-testnet.bybit.com"
    with pytest.raises(ValueError):
        AuthenticatedRESTTransport("BYBIT", "key", "secret", "https://api.bybit.com")


def test_exchange_specific_order_schemas_and_bybit_response_normalization():
    config = ExecutionConfig(mode=ExecutionMode.TESTNET, credentials={"api_key": "key", "api_secret": "secret"})
    binance = BinanceExecutionAdapter(config)
    bybit = BybitExecutionAdapter(config)
    order = OrderRequest.from_intent(intent(), exchange="BYBIT", mode=ExecutionMode.TESTNET)
    assert "newClientOrderId" in binance.order_params(order)
    assert "stopPrice" not in binance.order_params(order)
    assert bybit.order_params(order)["orderLinkId"] == order.client_order_id
    assert bybit.order_params(order)["orderType"] == "Market"
    normalized = bybit.normalize_order({"result": {"list": [{
        "symbol": "BTCUSDT", "orderId": "b1", "orderLinkId": "apex-b1",
        "side": "Sell", "orderType": "Market", "qty": "100", "cumExecQty": "30",
        "avgPrice": "101", "orderStatus": "PartiallyFilled",
    }]}})
    assert normalized.client_order_id == "apex-b1"
    assert normalized.status is OrderStatus.PARTIALLY_FILLED
    assert normalized.filled_quantity == 30
    assert BinanceExecutionAdapter(config).normalize_orders({"symbol": "BTCUSDT", "orderId": "1", "clientOrderId": "x", "side": "BUY", "origQty": "1", "status": "NEW"})[0].client_order_id == "x"


def test_binance_protection_translation_preserves_trigger_and_quantity_semantics():
    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    adapter = BinanceExecutionAdapter(config)
    stop = OrderRequest("stop", None, "BTCUSDT", "SELL", "STOP_MARKET", 0.1, stop_price=98, reduce_only=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    take_profit = OrderRequest("tp", None, "BTCUSDT", "SELL", "TAKE_PROFIT", 0.1, price=104, stop_price=104, reduce_only=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    assert adapter.order_submission_path(stop) == "/fapi/v1/algoOrder"
    assert adapter.order_params(stop) == {"algoType": "CONDITIONAL", "symbol": "BTCUSDT", "side": "SELL", "type": "STOP_MARKET", "clientAlgoId": "stop", "quantity": "0.1", "reduceOnly": "true", "triggerPrice": "98"}
    assert adapter.order_params(take_profit)["type"] == "TAKE_PROFIT"
    assert adapter.order_params(take_profit)["triggerPrice"] == "104"
    assert adapter.order_params(take_profit)["side"] == "SELL"
    assert adapter.order_params(take_profit)["quantity"] == "0.1"


def test_binance_algo_response_normalizes_client_and_trigger_fields():
    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    adapter = BinanceExecutionAdapter(config)
    order = adapter.normalize_order({"code": 0, "msg": "", "data": {"symbol": "BTCUSDT", "algoId": "algo-1", "clientAlgoId": "sl", "side": "SELL", "orderType": "STOP_MARKET", "quantity": "0.1", "triggerPrice": "98", "algoStatus": "NEW"}})
    assert order.exchange_order_id == "algo-1"
    assert order.client_order_id == "sl"
    assert order.stop_price == 98
    assert order.status is OrderStatus.NEW
    assert adapter.order_query_params("sl") == {"algoId": "algo-1"}


def test_binance_algo_creation_identifier_only_response_uses_request_context():
    def request(method, path, params):
        assert method == "POST"
        assert path == "/fapi/v1/algoOrder"
        return {"code": 0, "msg": "success", "data": {"algoId": "algo-2", "clientAlgoId": "sl-2"}}

    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    adapter = BinanceExecutionAdapter(config, transport=request)
    order = OrderRequest("sl-2", None, "BTCUSDT", "SELL", "STOP_MARKET", 0.1, stop_price=98, reduce_only=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    normalized = adapter.submit_order(order)
    assert normalized.symbol == "BTCUSDT"
    assert normalized.exchange_order_id == "algo-2"
    assert normalized.client_order_id == "sl-2"
    assert normalized.stop_price == 98


def test_binance_tp_algo_query_accepts_wrapped_list_and_uses_algo_id():
    calls = []

    def request(method, path, params):
        calls.append((method, path, params))
        if method == "POST":
            return {"code": 200, "msg": "success", "data": {"algoId": "tp-algo", "clientAlgoId": "tp-2"}}
        return {"code": 200, "data": [{"algoId": "tp-algo", "clientAlgoId": "tp-2", "symbol": "BTCUSDT", "side": "SELL", "orderType": "TAKE_PROFIT", "algoStatus": "NEW", "triggerPrice": "104", "price": "104", "quantity": "0.1", "reduceOnly": True}]}

    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    adapter = BinanceExecutionAdapter(config, transport=request)
    tp = OrderRequest("tp-2", None, "BTCUSDT", "SELL", "TAKE_PROFIT", 0.1, price=104, stop_price=104, reduce_only=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    adapter.submit_order(tp)
    queried = adapter.get_order("tp-2")
    assert queried.client_order_id == "tp-2"
    assert queried.exchange_order_id == "tp-algo"
    assert queried.order_type == "TAKE_PROFIT"
    assert queried.stop_price == 104
    assert calls[-1] == ("GET", "/fapi/v1/algoOrder", {"algoId": "tp-algo"})


def test_binance_algo_cancel_uses_algo_id_and_normalizes_identifier_only_response():
    calls = []

    def request(method, path, params):
        calls.append((method, path, params))
        if method == "POST":
            return {"code": 200, "msg": "success", "data": {"algoId": "sl-algo", "clientAlgoId": "sl-3"}}
        if method == "DELETE":
            return {"code": 200, "msg": "success", "data": {"algoId": "sl-algo", "clientAlgoId": "sl-3", "algoStatus": "CANCELED"}}
        return {"code": 200, "data": [{"algoId": "sl-algo", "clientAlgoId": "sl-3", "symbol": "BTCUSDT", "side": "SELL", "orderType": "STOP_MARKET", "algoStatus": "CANCELED", "triggerPrice": "98", "quantity": "0.1"}]}

    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    adapter = BinanceExecutionAdapter(config, transport=request)
    sl = OrderRequest("sl-3", None, "BTCUSDT", "SELL", "STOP_MARKET", 0.1, stop_price=98, reduce_only=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    adapter.submit_order(sl)
    canceled = adapter.cancel_order("sl-3")
    assert canceled.exchange_order_id == "sl-algo"
    assert canceled.status is OrderStatus.CANCELED
    assert calls[-1] == ("DELETE", "/fapi/v1/algoOrder", {"algoId": "sl-algo"})


def test_binance_rejects_over_precision_protection_values_instead_of_rounding():
    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    adapter = BinanceExecutionAdapter(config)
    order = OrderRequest("sl-precision", None, "BTCUSDT", "SELL", "STOP_MARKET", 0.0007, stop_price=76000.001, reduce_only=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    with pytest.raises(ValueError, match="trigger price"):
        adapter.order_params(order)


def test_binance_open_orders_includes_algo_orders():
    def request(method, path, params):
        if path == "/fapi/v1/openOrders":
            return []
        if path == "/fapi/v1/openAlgoOrders":
            return {"code": 0, "msg": "", "data": [{"symbol": "BTCUSDT", "algoId": "algo-1", "clientAlgoId": "sl", "side": "SELL", "orderType": "STOP_MARKET", "quantity": "0.1", "triggerPrice": "98", "algoStatus": "NEW"}]}
        raise AssertionError(f"unexpected request: {method} {path}")

    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    orders = BinanceExecutionAdapter(config, transport=request).get_open_orders()
    assert [order.client_order_id for order in orders] == ["sl"]


def test_binance_close_position_translation_omits_incompatible_fields():
    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    adapter = BinanceExecutionAdapter(config)
    close_stop = OrderRequest("close-stop", None, "BTCUSDT", "SELL", "STOP_MARKET", 0, stop_price=98, close_position=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    close_tp = OrderRequest("close-tp", None, "BTCUSDT", "SELL", "TAKE_PROFIT", 0, stop_price=104, close_position=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    stop_params = adapter.order_params(close_stop)
    tp_params = adapter.order_params(close_tp)
    assert stop_params["closePosition"] == "true"
    assert "quantity" not in stop_params and "reduceOnly" not in stop_params
    assert stop_params["triggerPrice"] == "98"
    assert tp_params["type"] == "TAKE_PROFIT_MARKET"
    assert tp_params["closePosition"] == "true"
    assert tp_params["triggerPrice"] == "104"
    assert "quantity" not in tp_params and "reduceOnly" not in tp_params


def test_testnet_reconciliation_reads_remote_positions():
    def request(method, path, params):
        if method == "GET" and path == "/fapi/v1/positionRisk":
            return {"positions": [{"symbol": "BTCUSDT", "positionAmt": "0", "entryPrice": "0"}]}
        return []

    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    result = BinanceExecutionAdapter(config, transport=request).reconcile()
    assert result.status == "MATCH"
    assert result.actual is None


def test_invalid_protection_contracts_are_rejected():
    with pytest.raises(ValueError):
        OrderRequest("bad-trigger", None, "BTCUSDT", "SELL", "STOP_MARKET", 1)
    with pytest.raises(ValueError):
        OrderRequest("bad-side", None, "BTCUSDT", "HOLD", "STOP_MARKET", 1, stop_price=98)
    with pytest.raises(ValueError):
        OrderRequest("bad-quantity", None, "BTCUSDT", "SELL", "STOP_MARKET", 0, stop_price=98)
    with pytest.raises(ValueError):
        OrderRequest("bad-close-quantity", None, "BTCUSDT", "SELL", "STOP_MARKET", 1, stop_price=98, close_position=True)
    with pytest.raises(ValueError):
        OrderRequest("bad-close-reduce", None, "BTCUSDT", "SELL", "STOP_MARKET", 0, stop_price=98, close_position=True, reduce_only=True)


def test_transport_normalizes_failures_without_secrets():
    def opener(*_args, **_kwargs):
        raise TimeoutError("secret should not appear")

    transport = AuthenticatedRESTTransport("BINANCE", "key", "secret", "https://testnet.binancefuture.com", opener=opener)
    with pytest.raises(ExecutionTransportError) as error:
        transport.request("GET", "/fapi/v2/account")
    assert error.value.category == "TIMEOUT"
    assert "secret" not in str(error.value)


def test_transport_preserves_sanitized_exchange_error_details():
    def opener(*_args, **_kwargs):
        raise HTTPError("https://testnet.binancefuture.com", 400, "bad order", {}, None)

    transport = AuthenticatedRESTTransport("BINANCE", "key", "secret", "https://testnet.binancefuture.com", opener=opener)
    with pytest.raises(ExecutionTransportError) as error:
        transport.request("POST", "/fapi/v1/order", {"symbol": "BTCUSDT"})
    assert error.value.exchange_code is None
    assert error.value.exchange_message is None


def test_transport_preserves_http_status_and_retry_after():
    class Headers:
        def get(self, name): return "2" if name == "Retry-After" else None

    def opener(*_args, **_kwargs):
        error = HTTPError("https://testnet.binancefuture.com", 429, "rate limited", Headers(), None)
        error.read = lambda: b'{"code": -1003, "msg": "too many requests"}'
        raise error

    transport = AuthenticatedRESTTransport("BINANCE", "key", "secret", "https://testnet.binancefuture.com", opener=opener)
    with pytest.raises(ExecutionTransportError) as error:
        transport.request("GET", "/fapi/v2/account")
    assert error.value.http_status == 429
    assert error.value.retry_after == "2"
    assert error.value.exchange_code == "-1003"


def test_transport_syncs_binance_clock_offset_before_signed_request():
    calls = []
    clock_values = iter((100.0, 100.1, 100.2))

    class Response:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return self.body

    def opener(request, timeout):
        calls.append(request.full_url)
        return Response(b'{"serverTime": 104000}') if request.full_url.endswith("/fapi/v1/time") else Response(b'{"assets": []}')

    transport = AuthenticatedRESTTransport("BINANCE", "key", "secret", "https://testnet.binancefuture.com", opener=opener, clock=lambda: next(clock_values))
    assert transport.sync_clock() == 3950.0
    assert transport._timestamp() == 104150
    assert calls[0].endswith("/fapi/v1/time")


def test_transport_rejects_unsafe_exchange_clock_drift():
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return b'{"serverTime": 200000}'

    transport = AuthenticatedRESTTransport("BINANCE", "key", "secret", "https://testnet.binancefuture.com", opener=lambda *_: Response(), clock=lambda: 100.0)
    with pytest.raises(ExecutionTransportError, match="clock"):
        transport.sync_clock()
    assert transport.clock_healthy is False


def test_coordinator_retains_sanitized_submission_error_without_retry():
    def request(method, path, params):
        if method == "POST":
            raise ExecutionTransportError("HTTP_ERROR", "Exchange HTTP request failed", exchange_code="-2021", exchange_message="Order would immediately trigger.")
        raise ExecutionTransportError("HTTP_ERROR", "Exchange HTTP request failed", exchange_code="-2013", exchange_message="Order does not exist.")

    config = ExecutionConfig(mode=ExecutionMode.TESTNET, symbol="BTCUSDT", credentials={"api_key": "key", "api_secret": "secret"})
    adapter = BinanceExecutionAdapter(config, transport=request)
    coordinator = ExecutionCoordinator(adapter, config)
    order = OrderRequest("diag-sl", None, "BTCUSDT", "SELL", "STOP_MARKET", 0.1, stop_price=98, reduce_only=True, exchange="BINANCE", execution_mode=ExecutionMode.TESTNET)
    outcome = coordinator.submit_order_request(order)
    assert outcome.status == "UNKNOWN"
    assert coordinator.last_transport_error.exchange_code == "-2021"
    assert coordinator.last_transport_error.exchange_message == "Order would immediately trigger."


def test_transport_timeout_enters_unknown_without_blind_resubmission():
    calls = []

    def request(method, path, params):
        calls.append((method, path))
        if path == "/fapi/v2/account":
            return {}
        raise ExecutionTransportError("TIMEOUT", "request timed out")

    config = ExecutionConfig(mode=ExecutionMode.TESTNET, credentials={"api_key": "key", "api_secret": "secret"}, symbol="BTCUSDT")
    adapter = BinanceExecutionAdapter(config, transport=request)
    from brain.execution import ExecutionCoordinator
    outcome = ExecutionCoordinator(adapter, config).submit_intent(intent(), now=1)
    assert outcome.reason == "ACCOUNT_STATE_INVALID"
    assert calls == [("GET", "/fapi/v2/account")]


def test_binance_and_bybit_testnet_methods_use_injected_transport():
    responses = {
        "GET /fapi/v2/account": {"assets": [{"asset": "USDT", "availableBalance": "10"}]},
        "GET /v5/account/wallet-balance": {"result": {"list": [{"coin": [{"coin": "USDT", "availableToWithdraw": "10"}]}]}},
    }

    def request(method, path, params):
        return responses.get(f"{method} {path}", {"symbol": "BTCUSDT", "orderId": "1", "clientOrderId": "x", "side": "BUY", "origQty": "1", "status": "NEW"})

    config = ExecutionConfig(mode=ExecutionMode.TESTNET, credentials={"api_key": "key", "api_secret": "secret"})
    assert BinanceExecutionAdapter(config, transport=request).get_balances()[0]["asset"] == "USDT"
    assert BybitExecutionAdapter(config, transport=request).get_balances()[0]["coin"][0]["coin"] == "USDT"
    order = OrderRequest.from_intent(intent(), exchange="BINANCE", mode=ExecutionMode.TESTNET)
    normalized = BinanceExecutionAdapter(config, transport=request).submit_order(order)
    assert normalized.exchange == "BINANCE"


def test_order_state_machine_rejects_terminal_regressions():
    machine = OrderStateMachine(OrderRequest.from_intent(intent()))
    machine.transition(OrderStatus.ACKNOWLEDGED)
    machine.transition(OrderStatus.FILLED)
    with pytest.raises(ValueError):
        machine.transition(OrderStatus.NEW)


def test_live_adapters_are_disabled_even_with_credentials():
    config = ExecutionConfig(mode=ExecutionMode.LIVE, live_enabled=True, credentials={"api_key": "key", "api_secret": "secret"})
    with pytest.raises(ValueError, match="LIVE execution adapters are disabled"):
        BinanceExecutionAdapter(config)


def test_persisted_binance_protection_identity_restores_algo_lookup(tmp_path):
    ledger = ExecutionLedger(str(tmp_path / "protection.sqlite3"))
    protection = OrderRequest("entry-sl", "algo-1", "BTCUSDT", "SELL", "STOP_MARKET", 0.1, stop_price=98, reduce_only=True, parent_client_order_id="entry")
    ledger.record_protection(protection)
    restored = ledger.load_protections("entry")
    adapter = BinanceExecutionAdapter()
    adapter.restore_protection_identity(restored[0].client_order_id, restored[0].exchange_order_id)
    assert adapter.order_query_path_for("entry-sl") == "/fapi/v1/algoOrder"
    assert adapter.order_query_params("entry-sl") == {"algoId": "algo-1"}


def test_metadata_enforcement_rejects_unsafe_binance_protection_values():
    adapter = BinanceExecutionAdapter()
    adapter.set_instrument_metadata(ExchangeMetadata("BTCUSDT", 0.5, 0.001, 0.001, 1))
    order = OrderRequest("bad", None, "BTCUSDT", "SELL", "STOP_MARKET", 0.0015, stop_price=98, reduce_only=True)
    with pytest.raises(ValueError, match="aligned"):
        adapter.submit_order(order)


def test_metadata_enforcement_applies_to_bybit_prices_and_limits():
    adapter = BybitExecutionAdapter()
    adapter.set_instrument_metadata(ExchangeMetadata("BTCUSDT", 0.5, 0.001, 0.001, 1))
    order = OrderRequest("bad", None, "BTCUSDT", "SELL", "TAKE_PROFIT", 2, price=104, stop_price=104, reduce_only=True)
    with pytest.raises(ValueError, match="maximum"):
        adapter.submit_order(order)


def test_metadata_service_parses_and_caches_binance_filters():
    calls = []

    def request(method, path, params):
        calls.append((method, path, params))
        return {"symbols": [{"symbol": "BTCUSDT", "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
            {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "10", "stepSize": "0.001"},
        ]}]}

    service = ExchangeMetadataService(request, clock=lambda: 10, max_age=60)
    metadata = service.get("BINANCE", "BTCUSDT")
    assert metadata.tick_size == 0.1
    assert metadata.minimum_quantity == 0.001
    assert service.get("BINANCE", "BTCUSDT") == metadata
    assert len(calls) == 1


def test_metadata_service_parses_bybit_and_fails_closed_on_missing_filters():
    def request(method, path, params):
        return {"result": {"list": [{"symbol": "BTCUSDT", "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "maxOrderQty": "100"}, "priceFilter": {"tickSize": "0.5"}}]}}

    metadata = ExchangeMetadataService(request).get("BYBIT", "BTCUSDT")
    assert metadata.tick_size == 0.5
    assert metadata.maximum_quantity == 100
    with pytest.raises(ValueError, match="Missing Binance"):
        ExchangeMetadataService(lambda *_: {"symbols": []}).get("BINANCE", "BTCUSDT")
