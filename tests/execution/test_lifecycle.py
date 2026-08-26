import sqlite3
from dataclasses import replace

import pytest

from brain.execution import ExecutionConfig, ExecutionCoordinator, ExecutionLedger, ExecutionMode, OrderRequest, OrderStatus, PaperExecutionAdapter, PositionSnapshot
from brain.risk import RiskConfig, RiskGate
from tests.execution.test_p3_foundation import intent


def test_paper_adapter_uses_canonical_order_lifecycle_and_position():
    ledger = ExecutionLedger()
    coordinator = ExecutionCoordinator(PaperExecutionAdapter(), ExecutionConfig(), ledger)
    outcome = coordinator.submit_intent(intent(), now=10)
    assert outcome.status == "SUBMITTED"
    assert outcome.order.status.value == "FILLED"
    assert outcome.order.filled_quantity == outcome.order.quantity
    assert ledger.snapshot()[-1]["event_type"] == "FILLED"
    assert coordinator.reconcile().actual.quantity == outcome.order.quantity


def test_ledger_is_deterministically_serializable():
    ledger = ExecutionLedger()
    ledger.record("INTENT_CREATED", event_time=1, symbol="BTCUSDT", reason="signal")
    assert ledger.snapshot() == [{
        "event_type": "INTENT_CREATED", "client_order_id": None, "event_time": 1,
        "details": {"reason": "signal", "symbol": "BTCUSDT"},
    }]


def test_sqlite_ledger_recovers_events_after_restart(tmp_path):
    path = str(tmp_path / "execution.sqlite3")
    first = ExecutionLedger(path)
    first.record("ORDER_SUBMITTED", client_order_id="apex-1", event_time=2, symbol="BTCUSDT")
    second = ExecutionLedger(path)
    assert second.snapshot() == [{
        "event_type": "ORDER_SUBMITTED", "client_order_id": "apex-1", "event_time": 2,
        "details": {"symbol": "BTCUSDT"},
    }]


def test_coordinator_can_use_configured_durable_ledger(tmp_path):
    path = str(tmp_path / "coordinator.sqlite3")
    config = ExecutionConfig(state_db_path=path)
    coordinator = ExecutionCoordinator(PaperExecutionAdapter(), config)
    coordinator.submit_intent(intent(), now=3)
    recovered = ExecutionLedger(path)
    assert recovered.snapshot()[-1]["event_type"] == "FILLED"


def test_durable_state_recovers_order_and_position_after_restart(tmp_path):
    path = str(tmp_path / "durable.sqlite3")
    config = ExecutionConfig(state_db_path=path)
    coordinator = ExecutionCoordinator(PaperExecutionAdapter(), config)
    outcome = coordinator.submit_intent(intent(), now=11)

    assert outcome.status == "SUBMITTED"
    recovered = ExecutionCoordinator(PaperExecutionAdapter(), config)

    order = recovered.ledger.load_order(outcome.order.client_order_id)
    position = recovered.ledger.load_position("BTCUSDT")
    assert order is not None
    assert order.status.value == "FILLED"
    assert position is not None
    assert position.quantity == outcome.order.quantity
    assert recovered.recovery_state == "READY"


def test_recovery_mode_halts_trading_until_reconciliation_is_known(tmp_path):
    path = str(tmp_path / "recovery.sqlite3")
    ledger = ExecutionLedger(path)
    ledger.record_reconciliation(
        "BTCUSDT",
        status="UNKNOWN",
        details={"reason": "remote state not yet verified"},
        symbol="BTCUSDT",
    )

    coordinator = ExecutionCoordinator(PaperExecutionAdapter(), ExecutionConfig(state_db_path=path))
    assert coordinator.recovery_state == "RECOVERY"
    outcome = coordinator.submit_intent(intent(), now=12)
    assert outcome.reason == "RECOVERY_REQUIRED"


class PartialAdapter(PaperExecutionAdapter):
    def __init__(self, fills):
        super().__init__()
        self.fills = list(fills)

    def submit_order(self, order):
        submitted = replace(order, status=OrderStatus.PARTIALLY_FILLED, filled_quantity=self.fills[0], average_fill_price=order.price)
        self.orders[order.client_order_id] = submitted
        self.positions = [PositionSnapshot(order.symbol, "LONG", submitted.filled_quantity, order.price, self.exchange)]
        return submitted


def test_partial_fill_is_persisted_at_actual_quantity(tmp_path):
    path = str(tmp_path / "partial.sqlite3")
    adapter = PartialAdapter([0.003])
    outcome = ExecutionCoordinator(adapter, ExecutionConfig(state_db_path=path)).submit_intent(intent(), now=1)
    ledger = ExecutionLedger(path)
    assert outcome.status == "SUBMITTED"
    assert ledger.filled_quantity(outcome.order.client_order_id) == 0.003
    assert ledger.load_position("BTCUSDT").quantity == 0.003


def test_duplicate_and_out_of_order_fills_are_deterministic(tmp_path):
    ledger = ExecutionLedger(str(tmp_path / "fills.sqlite3"))
    ledger.record_fill(fill_id="b", exchange="PAPER", symbol="BTCUSDT", client_order_id="entry", side="BUY", quantity=0.002, price=101, event_time=2)
    ledger.record_fill(fill_id="a", exchange="PAPER", symbol="BTCUSDT", client_order_id="entry", side="BUY", quantity=0.003, price=100, event_time=1)
    ledger.record_fill(fill_id="a", exchange="PAPER", symbol="BTCUSDT", client_order_id="entry", side="BUY", quantity=0.003, price=100, event_time=1)
    assert ledger.filled_quantity("entry") == 0.005
    assert [fill.fill_id for fill in ledger.load_fills("entry")] == ["a", "b"]


def test_restart_recovery_upgrades_protection_after_new_fill(tmp_path):
    path = str(tmp_path / "restart.sqlite3")
    adapter = PartialAdapter([0.003])
    config = ExecutionConfig(state_db_path=path)
    first = ExecutionCoordinator(adapter, config)
    outcome = first.submit_intent(intent(), now=1)
    assert outcome.reason is None
    adapter.orders[outcome.order.client_order_id] = replace(outcome.order, status=OrderStatus.FILLED, filled_quantity=0.005)
    adapter.positions[0] = replace(adapter.positions[0], quantity=0.005)
    restarted = ExecutionCoordinator(adapter, config)
    assert restarted.recover(intent(), client_order_id=outcome.order.client_order_id, now=2)
    assert restarted.ledger.filled_quantity(outcome.order.client_order_id) == 0.005
    assert restarted.recovery_state == "READY"


def test_kill_switch_state_survives_restart_and_allows_reduce_only(tmp_path):
    path = str(tmp_path / "kill.sqlite3")
    ledger = ExecutionLedger(path)
    gate = RiskGate(RiskConfig(), ledger=ledger)
    gate.kill("drawdown")
    assert RiskGate(RiskConfig(), ledger=ExecutionLedger(path)).killed is True
    coordinator = ExecutionCoordinator(PaperExecutionAdapter(), ExecutionConfig(state_db_path=path))
    assert coordinator.submit_intent(intent()).reason == "KILL_SWITCH"
    reduction = OrderRequest("close-1", None, "BTCUSDT", "SELL", "MARKET", 0.1, reduce_only=True)
    assert coordinator.submit_order_request(reduction).status == "SUBMITTED"


def test_terminal_protection_is_not_treated_as_active():
    adapter = PaperExecutionAdapter()
    coordinator = ExecutionCoordinator(adapter)
    entry = coordinator.submit_intent(intent(), now=1).order
    protection = coordinator.protection.create_plan(intent(), quantity=entry.filled_quantity)[1:]
    for order in protection:
        adapter.orders[order.client_order_id] = replace(order, status=OrderStatus.CANCELED, filled_quantity=order.quantity)
    assert coordinator.synchronize_protection(intent(), entry, now=2) is False
    assert coordinator.recovery_state == "RECOVERY"


def test_ledger_backup_preserves_safety_state(tmp_path):
    source = ExecutionLedger(str(tmp_path / "source.sqlite3"))
    source.record("AUDIT", event_time=1, symbol="BTCUSDT")
    source.record_kill_switch("KILLED", "operator", event_time=2)
    backup = str(tmp_path / "backup.sqlite3")
    source.backup_to(backup)
    restored = ExecutionLedger(backup)
    assert restored.snapshot()[0]["event_type"] == "AUDIT"
    assert restored.kill_switch_state == "KILLED"
    assert restored.integrity_check() is True


def test_safety_rejection_is_durably_audited(tmp_path):
    path = str(tmp_path / "rejections.sqlite3")
    config = ExecutionConfig(mode=ExecutionMode.LIVE)
    coordinator = ExecutionCoordinator(PaperExecutionAdapter(), config, ExecutionLedger(path))
    outcome = coordinator.submit_intent(intent(), now=4)
    restored = ExecutionLedger(path)
    assert outcome.reason == "LIVE_NOT_EXPLICITLY_ENABLED"
    assert restored.snapshot()[-1]["event_type"] == "EXECUTION_REJECTED"
    assert restored.snapshot()[-1]["details"]["reason"] == "LIVE_NOT_EXPLICITLY_ENABLED"


def test_critical_ledger_events_notify_without_leaking_details():
    alerts = []
    ledger = ExecutionLedger(event_listener=alerts.append)
    ledger.record("EXECUTION_FAILURE", client_order_id="order-1", event_time=1, symbol="BTCUSDT", reason="TIMEOUT", api_secret="secret")
    assert len(alerts) == 1
    assert alerts[0].details == {"reason": "TIMEOUT", "symbol": "BTCUSDT"}
    assert "secret" not in repr(alerts[0])


def test_alert_listener_failure_does_not_break_durable_event():
    def failing_listener(_event):
        raise RuntimeError("alert unavailable")

    ledger = ExecutionLedger(event_listener=failing_listener)
    assert ledger.record("KILL_SWITCH", event_time=1, reason="drawdown").event_type == "KILL_SWITCH"


def test_ledger_rejects_divergent_replay_state(tmp_path):
    path = str(tmp_path / "event_consistency.sqlite3")
    ledger = ExecutionLedger(path)
    fill = ledger.create_fill(symbol="BTCUSDT", client_order_id="evt-1", side="BUY", quantity=0.25, price=100.0, event_time=11.0)
    ledger.record_fill(fill=fill, symbol="BTCUSDT", client_order_id="evt-1", side="BUY", quantity=0.25, price=100.0, event_time=11.0)
    ledger.persist_position(PositionSnapshot("BTCUSDT", "LONG", 0.25, 100.0, "PAPER"))
    ledger._connection.execute("UPDATE positions SET quantity = 0.50 WHERE symbol = 'BTCUSDT'")
    ledger._connection.commit()
    with pytest.raises(ValueError, match="State mismatch|divergent|corrupt|mismatch"):
        ledger.snapshot()


def test_ledger_rejects_corrupted_event_payloads(tmp_path):
    path = str(tmp_path / "event_payload.sqlite3")
    ledger = ExecutionLedger(path)
    ledger.record("FILLED", client_order_id="evt-2", event_time=12.0, quantity=0.10)
    ledger._connection.execute("UPDATE execution_events SET details_json = '{bad-json' WHERE client_order_id = 'evt-2'")
    ledger._connection.commit()
    with pytest.raises(ValueError, match="Corrupted|corrupt|malformed|event"):
        ledger.snapshot()


def test_ledger_persists_intent_and_order_atomically(tmp_path):
    ledger = ExecutionLedger(str(tmp_path / "intent_order.sqlite3"))
    entry = ExecutionCoordinator(PaperExecutionAdapter(), ExecutionConfig(state_db_path=str(tmp_path / "intent_order.sqlite3"))).submit_intent(intent(), now=2)
    saved_intent = ledger.load_intent(entry.order.client_order_id)
    saved_order = ledger.load_order(entry.order.client_order_id)
    assert saved_intent is not None
    assert saved_order is not None
    assert saved_intent.status == "APPROVED"
    assert saved_order.status.value == "FILLED"


def test_confirmed_fill_transaction_rolls_back_on_failure(tmp_path):
    ledger = ExecutionLedger(str(tmp_path / "atomic_fill.sqlite3"))
    fill = ledger.create_fill(
        symbol="BTCUSDT",
        client_order_id="fill-rollback",
        side="BUY",
        quantity=0.25,
        price=100.0,
        event_time=9.0,
    )
    position = PositionSnapshot("BTCUSDT", "LONG", 0.25, 100.0, "PAPER")

    class FailingPositionConnection:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def execute(self, sql, params=()):
            if "INSERT INTO positions" in sql:
                raise sqlite3.DatabaseError("simulated write failure")
            return self._wrapped.execute(sql, params)

        def commit(self):
            return self._wrapped.commit()

        def rollback(self):
            return self._wrapped.rollback()

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

    ledger._connection = FailingPositionConnection(ledger._connection)
    with pytest.raises(sqlite3.DatabaseError):
        ledger.record_confirmed_fill(fill, position, "FILLED", {"quantity": 0.25}, "MATCH", {"client_order_id": "fill-rollback"}, 9.0)

    assert ledger.load_fills("fill-rollback") == ()
    assert ledger.load_position("BTCUSDT") is None
