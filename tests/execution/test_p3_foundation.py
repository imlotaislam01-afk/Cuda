from dataclasses import replace

import pytest

from brain.execution import (
    BinanceExecutionAdapter,
    BybitExecutionAdapter,
    CredentialError,
    ExecutionConfig,
    ExecutionCoordinator,
    ExecutionIntent,
    ExecutionMode,
    InMemoryExecutionAdapter,
    OrderRequest,
    OrderStatus,
    PositionSnapshot,
    ProtectionManager,
    deterministic_client_order_id,
    DiscrepancyCategory,
    reconcile_positions,
)


def intent():
    return ExecutionIntent("BTCUSDT", "LONG", 100, 98, 104, 106, None, 1, 5, 2, approved=True)


def test_order_model_and_identity_are_deterministic():
    order = OrderRequest.from_intent(intent())
    assert order.client_order_id == deterministic_client_order_id(intent())
    assert order.side == "BUY"
    assert order.to_dict() == OrderRequest.from_intent(intent()).to_dict()


def test_coordinator_blocks_default_live_and_kill_switches():
    live = ExecutionCoordinator(InMemoryExecutionAdapter(), ExecutionConfig(mode=ExecutionMode.LIVE))
    assert live.submit_intent(intent()).reason == "LIVE_NOT_EXPLICITLY_ENABLED"
    killed = ExecutionCoordinator(InMemoryExecutionAdapter(), ExecutionConfig(global_kill_switch=True))
    assert killed.submit_intent(intent()).reason == "KILL_SWITCH"


def test_coordinator_prevents_duplicates_and_stale_intents():
    adapter = InMemoryExecutionAdapter()
    coordinator = ExecutionCoordinator(adapter)
    first = coordinator.submit_intent(intent(), now=10)
    duplicate = coordinator.submit_intent(intent(), now=10)
    stale = ExecutionCoordinator(adapter, ExecutionConfig(stale_intent_after=2)).submit_intent(intent(), as_of=1, now=10)
    assert first.status == "SUBMITTED"
    assert duplicate.status == "DUPLICATE"
    assert stale.reason == "STALE_INTENT"


def test_timeout_after_submit_reconciles_without_duplicate():
    class TimeoutAdapter(InMemoryExecutionAdapter):
        def submit_order(self, order):
            self.orders[order.client_order_id] = order
            raise TimeoutError("ack lost")

    outcome = ExecutionCoordinator(TimeoutAdapter()).submit_intent(intent())
    assert outcome.status == "RECONCILED"
    assert outcome.order.status == OrderStatus.NEW


def test_timeout_with_unavailable_order_query_is_unknown_and_blocks_retry():
    class AmbiguousAdapter(InMemoryExecutionAdapter):
        def submit_order(self, order):
            raise TimeoutError("ack lost")

        def get_order(self, client_order_id):
            raise ConnectionError("order query unavailable")

    coordinator = ExecutionCoordinator(AmbiguousAdapter())
    outcome = coordinator.submit_intent(intent(), now=10)

    assert outcome.status == "UNKNOWN"
    assert outcome.reason == "SUBMISSION_STATUS_UNKNOWN"
    assert coordinator.recovery_state == "RECOVERY"
    assert coordinator.submit_intent(intent(), now=11).reason == "RECOVERY_REQUIRED"


def test_reconciliation_detects_position_discrepancies():
    adapter = InMemoryExecutionAdapter()
    adapter.positions.append(PositionSnapshot("BTCUSDT", "LONG", 0.5, 100, "PAPER"))
    result = adapter.reconcile(PositionSnapshot("BTCUSDT", "LONG", 1, 100, "PAPER"))
    assert result.status == "DISCREPANCY"
    assert result.discrepancies == ("QUANTITY_MISMATCH",)


def test_reconciliation_categories_are_typed_and_serializable():
    result = reconcile_positions(PositionSnapshot("BTCUSDT", "LONG", 1, 100, "PAPER"), [PositionSnapshot("BTCUSDT", "LONG", 0.5, 100, "PAPER")])
    assert result.discrepancies == (DiscrepancyCategory.POSITION_QUANTITY_MISMATCH,)
    assert result.to_dict()["discrepancies"] == ["QUANTITY_MISMATCH"]


def test_reconciliation_matches_expected_symbol_across_position_collection():
    expected = PositionSnapshot("BTCUSDT", "LONG", 1, 100, "PAPER")
    actual = [PositionSnapshot("ETHUSDT", "LONG", 2, 200, "PAPER"), expected]
    result = reconcile_positions(expected, actual)
    assert result.actual.symbol == "BTCUSDT"
    assert DiscrepancyCategory.UNEXPECTED_POSITION in result.discrepancies


def test_protection_requires_stop_and_target_and_verifies_them():
    manager = ProtectionManager()
    orders = manager.create_plan(intent())
    assert manager.verify(orders[0], orders).verified is True
    assert manager.verify(orders[0], ()).reason == "PROTECTION_MISSING"
    with pytest.raises(ValueError):
        manager.create_plan(replace(intent(), approved=False))


def test_paper_shadow_and_testnet_live_credentials_are_explicit():
    assert ExecutionConfig().mode is ExecutionMode.PAPER
    assert ExecutionConfig(mode=ExecutionMode.SHADOW).allows_submission("PAPER", "BTCUSDT")
    with pytest.raises(CredentialError):
        BybitExecutionAdapter(ExecutionConfig(mode=ExecutionMode.TESTNET))
    with pytest.raises(CredentialError):
        BinanceExecutionAdapter(ExecutionConfig(mode=ExecutionMode.LIVE, live_enabled=True))


def test_binance_and_bybit_normalize_canonical_orders():
    response = {"symbol": "btcusdt", "orderId": 7, "clientOrderId": "apex-x", "side": "BUY", "type": "MARKET", "origQty": "1", "executedQty": "0.5", "avgPrice": "100", "status": "PARTIALLY_FILLED"}
    for adapter in (BinanceExecutionAdapter(), BybitExecutionAdapter()):
        order = adapter.normalize_order(response)
        assert order.exchange == adapter.exchange
        assert order.status is OrderStatus.PARTIALLY_FILLED
        assert order.filled_quantity == 0.5


def test_invalid_health_and_unapproved_orders_never_submit():
    adapter = InMemoryExecutionAdapter()
    adapter.healthy = False
    assert ExecutionCoordinator(adapter).submit_intent(intent()).reason == "EXCHANGE_UNAVAILABLE"
    assert ExecutionCoordinator(InMemoryExecutionAdapter()).submit_intent(replace(intent(), approved=False)).reason == "RISK_NOT_APPROVED"


def test_paper_mode_cannot_reach_a_network_transport():
    calls = []
    adapter = BinanceExecutionAdapter(ExecutionConfig(mode=ExecutionMode.PAPER), transport=lambda *args: calls.append(args))
    outcome = ExecutionCoordinator(adapter).submit_intent(intent())
    assert outcome.status == "SUBMITTED"
    assert calls == []


def test_coordinator_preserves_rejected_and_unknown_exchange_statuses():
    class StatusAdapter(InMemoryExecutionAdapter):
        def __init__(self, status):
            super().__init__()
            self.status = status

        def submit_order(self, order):
            from dataclasses import replace
            return replace(order, status=self.status)

    rejected = ExecutionCoordinator(StatusAdapter(OrderStatus.REJECTED)).submit_intent(intent())
    unknown = ExecutionCoordinator(StatusAdapter(OrderStatus.UNKNOWN)).submit_intent(intent())
    assert rejected.status == "REJECTED"
    assert unknown.status == "UNKNOWN"


def test_direct_non_reduce_only_order_cannot_bypass_intent_gate():
    adapter = InMemoryExecutionAdapter()
    order = OrderRequest("direct", None, "BTCUSDT", "BUY", "MARKET", 1)
    outcome = ExecutionCoordinator(adapter).submit_order_request(order)
    assert outcome.reason == "DIRECT_ENTRY_REQUIRES_INTENT"
    assert adapter.orders == {}


def test_incomplete_account_state_fails_closed_before_submission():
    class IncompleteAccountAdapter(InMemoryExecutionAdapter):
        def get_account_state(self):
            return {"healthy": True}

    outcome = ExecutionCoordinator(IncompleteAccountAdapter()).submit_intent(intent())
    assert outcome.reason == "ACCOUNT_STATE_INVALID"
