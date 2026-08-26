from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

from .adapter import ExchangeExecutionAdapter
from .model import ExecutionConfig, ExecutionMode, OrderRequest, OrderStatus, PositionSnapshot, ReconciliationResult
from .lifecycle import ExecutionLedger
from .protection import ProtectionManager
from .transport import ExecutionTransportError


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    order: OrderRequest | None = None
    reason: str | None = None

    def to_dict(self):
        return {"status": self.status, "order": self.order.to_dict() if self.order else None, "reason": self.reason}


class ExecutionCoordinator:
    """Single safety gate and idempotent entry point for exchange execution."""

    def __init__(self, adapter: ExchangeExecutionAdapter, config: ExecutionConfig | None = None, ledger: ExecutionLedger | None = None) -> None:
        self.adapter = adapter
        self.config = config or ExecutionConfig()
        self._requests: dict[str, str] = {}
        self.ledger = ledger or ExecutionLedger(self.config.state_db_path)
        self.protection = ProtectionManager()
        self.last_transport_error: ExecutionTransportError | None = None
        self.recovery_state = self.ledger.recovery_state

    def _reject(self, symbol: str, reason: str, now: float) -> ExecutionOutcome:
        self.ledger.record("EXECUTION_REJECTED", event_time=now, symbol=symbol.upper(), reason=reason)
        return ExecutionOutcome("REJECTED", reason=reason)

    def _check_recovery_gate(self, *, symbol: str, now: float = 0.0, reason: str = "RECOVERY_REQUIRED") -> bool:
        if self.recovery_state == "RECOVERY":
            self.ledger.record("RECOVERY_REQUIRED", event_time=now, symbol=symbol.upper(), reason=reason)
            self.ledger.record_recovery_event("RECOVERY", reason, event_time=now, payload={"symbol": symbol.upper(), "reason": reason})
            self.recovery_state = "RECOVERY"
            return False
        return True

    def submit_intent(self, intent, *, as_of: float | None = None, now: float = 0.0) -> ExecutionOutcome:
        if not self._check_recovery_gate(symbol=intent.symbol, now=now):
            return ExecutionOutcome("REJECTED", reason="RECOVERY_REQUIRED")
        if self.ledger.kill_switch_state == "KILLED":
            return ExecutionOutcome("REJECTED", reason="KILL_SWITCH")
        if not intent.approved:
            self.ledger.record("RISK_REJECTED", event_time=now, reason="RISK_NOT_APPROVED")
            return ExecutionOutcome("REJECTED", reason="RISK_NOT_APPROVED")
        if self.config.mode is ExecutionMode.LIVE and not self.config.allows_submission(self.adapter.exchange, intent.symbol):
            return self._reject(intent.symbol, "LIVE_NOT_EXPLICITLY_ENABLED", now)
        if not self.config.allows_submission(self.adapter.exchange, intent.symbol):
            return self._reject(intent.symbol, "EXECUTION_MODE_DISABLED", now)
        if self.config.global_kill_switch or self.config.exchange_kill_switch or intent.symbol.upper() in self.config.symbol_kill_switches:
            self.ledger.record("KILL_SWITCH", event_time=now, symbol=intent.symbol)
            return ExecutionOutcome("REJECTED", reason="KILL_SWITCH")
        if as_of is not None and now - as_of > self.config.stale_intent_after:
            return self._reject(intent.symbol, "STALE_INTENT", now)
        if intent.quantity <= 0 or intent.entry <= 0 or intent.stop_loss <= 0:
            return self._reject(intent.symbol, "INVALID_ORDER_LEVELS", now)
        notional = float(intent.quantity) * float(intent.entry)
        if self.config.max_order_notional > 0 and notional > self.config.max_order_notional:
            return self._reject(intent.symbol, "ORDER_NOTIONAL_LIMIT", now)
        if self.config.max_position_notional > 0 and notional > self.config.max_position_notional:
            return self._reject(intent.symbol, "POSITION_NOTIONAL_LIMIT", now)
        if intent.leverage > self.config.max_leverage:
            return self._reject(intent.symbol, "LEVERAGE_LIMIT", now)
        order = OrderRequest.from_intent(intent, exchange=self.adapter.exchange, mode=self.config.mode, created_time=now)
        fingerprint = str(order.to_dict())
        if order.client_order_id in self._requests:
            existing = self.adapter.get_order(order.client_order_id)
            if existing is not None:
                return ExecutionOutcome("DUPLICATE", existing, "DUPLICATE_INTENT")
            return ExecutionOutcome("REJECTED", reason="AMBIGUOUS_RETRY_REQUIRES_RECONCILIATION")
        if not self.adapter.health_check():
            return self._reject(intent.symbol, "EXCHANGE_UNAVAILABLE", now)
        try:
            account = self.adapter.get_account_state()
        except (TimeoutError, ConnectionError, ExecutionTransportError):
            self.ledger.record("EXECUTION_FAILURE", event_time=now, reason="EXCHANGE_UNAVAILABLE")
            return self._reject(intent.symbol, "EXCHANGE_UNAVAILABLE", now)
        try:
            available_balance = float(account["available_balance"])
        except (KeyError, TypeError, ValueError):
            return self._reject(intent.symbol, "ACCOUNT_STATE_INVALID", now)
        if (not isfinite(available_balance) and self.config.mode not in {ExecutionMode.PAPER, ExecutionMode.SHADOW}) or available_balance < 0:
            return self._reject(intent.symbol, "ACCOUNT_STATE_INVALID", now)
        if available_balance < notional / max(float(intent.leverage), 1.0):
            return self._reject(intent.symbol, "INSUFFICIENT_BALANCE", now)
        self._requests[order.client_order_id] = fingerprint
        self.ledger.persist_intent(intent, client_order_id=order.client_order_id, status="APPROVED", created_at=now)
        self.ledger.record("EXECUTION_APPROVED", client_order_id=order.client_order_id, event_time=now, exchange=self.adapter.exchange)
        self.ledger.persist_order(order)
        try:
            submitted = self.adapter.submit_order(order)
        except (TimeoutError, ConnectionError, ExecutionTransportError, ValueError) as error:
            self.last_transport_error = error if isinstance(error, ExecutionTransportError) else None
            try:
                existing = self.adapter.get_order(order.client_order_id)
            except (TimeoutError, ConnectionError, ExecutionTransportError):
                existing = None
            if existing is not None:
                self.ledger.record("RECONCILIATION", client_order_id=order.client_order_id, event_time=now, status="RECONCILED")
                self.ledger.record_reconciliation(order.symbol, status="MATCH", details={"client_order_id": order.client_order_id, "source": "timeout_reconciled"}, event_time=now)
                self.recovery_state = self.ledger.recovery_state
                return ExecutionOutcome("RECONCILED", existing, "TIMEOUT_RECONCILED")
            self.ledger.record("EXECUTION_FAILURE", client_order_id=order.client_order_id, event_time=now, reason="SUBMISSION_STATUS_UNKNOWN")
            self.ledger.record_reconciliation(order.symbol, status="UNKNOWN", details={"client_order_id": order.client_order_id, "reason": "SUBMISSION_STATUS_UNKNOWN"}, event_time=now)
            self.recovery_state = self.ledger.recovery_state
            return ExecutionOutcome("UNKNOWN", reason="SUBMISSION_STATUS_UNKNOWN")
        self.ledger.persist_order(submitted)
        self.ledger.record("ORDER_SUBMITTED", client_order_id=order.client_order_id, event_time=now, status=submitted.status.value)
        if submitted.status is OrderStatus.REJECTED:
            self.ledger.record("ORDER_REJECTED", client_order_id=order.client_order_id, event_time=now)
            return ExecutionOutcome("REJECTED", submitted, "EXCHANGE_REJECTED")
        if submitted.status is OrderStatus.UNKNOWN:
            self.ledger.record_reconciliation(order.symbol, status="UNKNOWN", details={"client_order_id": order.client_order_id, "reason": "ORDER_STATUS_UNKNOWN"}, event_time=now)
            self.recovery_state = "RECOVERY"
            return ExecutionOutcome("UNKNOWN", submitted, "SUBMISSION_STATUS_UNKNOWN")
        self.process_confirmed_fill(submitted, now=now, source="SUBMIT")
        if submitted.status is OrderStatus.PARTIALLY_FILLED:
            protection = self.synchronize_protection(intent, submitted, now=now)
            if not protection:
                return ExecutionOutcome("UNKNOWN", submitted, "RECOVERY_REQUIRED")
        return ExecutionOutcome("SUBMITTED", submitted)

    def process_confirmed_fill(self, order: OrderRequest, *, now: float = 0.0, source: str = "EXCHANGE") -> float:
        """Apply only the newly observed cumulative fill quantity to durable state."""
        if order.reduce_only or order.filled_quantity <= 0:
            return 0.0
        previous = self.ledger.filled_quantity(order.client_order_id)
        delta = float(order.filled_quantity) - previous
        if delta < 0:
            self.ledger.record_reconciliation(order.symbol, status="UNKNOWN", details={"reason": "FILL_QUANTITY_REGRESSED", "client_order_id": order.client_order_id}, event_time=now)
            self.recovery_state = "RECOVERY"
            return 0.0
        if delta == 0:
            return 0.0
        price = order.average_fill_price or order.price
        if price is None:
            self.ledger.record_reconciliation(order.symbol, status="UNKNOWN", details={"reason": "FILL_PRICE_UNKNOWN", "client_order_id": order.client_order_id}, event_time=now)
            self.recovery_state = "RECOVERY"
            return 0.0
        fill = self.ledger.create_fill(symbol=order.symbol, client_order_id=order.client_order_id, side=order.side, quantity=delta, price=price, event_time=now, exchange=self.adapter.exchange, order_id=order.exchange_order_id, source=source)
        total = previous + delta
        position = PositionSnapshot(order.symbol, "LONG" if order.side == "BUY" else "SHORT", total, price, self.adapter.exchange, "OPEN")
        event_type = "FILLED" if order.status is OrderStatus.FILLED else "PARTIALLY_FILLED"
        reconciliation_status = "MATCH" if order.status is OrderStatus.FILLED else "UNKNOWN"
        reconciliation_details = {"client_order_id": order.client_order_id, "filled_quantity": total}
        if order.status is not OrderStatus.FILLED:
            reconciliation_details["reason"] = "PARTIAL_FILL_PENDING"
        self.ledger.record_confirmed_fill(fill, position, event_type, {"quantity": delta, "cumulative_quantity": total}, reconciliation_status, reconciliation_details, now)
        self.recovery_state = self.ledger.recovery_state
        return delta

    def synchronize_protection(self, intent, entry: OrderRequest, *, now: float = 0.0) -> bool:
        """Create or amend reduce-only protection to the confirmed entry quantity."""
        quantity = self.ledger.filled_quantity(entry.client_order_id)
        if quantity <= 0:
            return True
        try:
            plan = self.protection.create_plan(intent, exchange=self.adapter.exchange, mode=self.config.mode, quantity=quantity)[1:]
            remote = []
            for desired in plan:
                existing = self.adapter.get_order(desired.client_order_id)
                if existing is not None and existing.quantity < quantity:
                    existing = self.adapter.amend_order(desired)
                elif existing is None:
                    existing = self.submit_order_request(desired, now=now).order
                if existing is None or existing.status not in {OrderStatus.NEW, OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED} or existing.quantity < quantity:
                    raise RuntimeError("protection not confirmed")
                self.ledger.record_protection(existing)
                remote.append(existing)
            verification_entry = OrderRequest.from_intent(intent, exchange=self.adapter.exchange, mode=self.config.mode)
            verification_entry = verification_entry.__class__(**{**vars(verification_entry), "filled_quantity": quantity, "status": entry.status})
            if not self.protection.verify(verification_entry, remote).verified:
                raise RuntimeError("protection verification failed")
            self.ledger.record_reconciliation(entry.symbol, status="MATCH", details={"client_order_id": entry.client_order_id, "protection_quantity": quantity}, event_time=now)
            self.recovery_state = self.ledger.recovery_state
            return True
        except (TimeoutError, ConnectionError, KeyError, RuntimeError, ValueError):
            self.ledger.record_reconciliation(entry.symbol, status="UNKNOWN", details={"client_order_id": entry.client_order_id, "reason": "PROTECTION_UNCONFIRMED"}, event_time=now)
            self.recovery_state = "RECOVERY"
            return False

    def recover(self, intent, *, client_order_id: str | None = None, now: float = 0.0) -> bool:
        """Rebuild a durable entry from the exchange and repair protection before resuming."""
        order_id = client_order_id or OrderRequest.from_intent(intent, exchange=self.adapter.exchange, mode=self.config.mode).client_order_id
        try:
            remote_order = self.adapter.get_order(order_id)
            if remote_order is None or remote_order.status is OrderStatus.UNKNOWN:
                raise RuntimeError("entry state unknown")
            self.ledger.persist_order(remote_order)
            restore = getattr(self.adapter, "restore_protection_identity", None)
            if restore is not None:
                for protection in self.ledger.load_protections(order_id):
                    if protection.exchange_order_id is not None:
                        restore(protection.client_order_id, protection.exchange_order_id)
            self.process_confirmed_fill(remote_order, now=now, source="RECOVERY")
            if remote_order.filled_quantity > 0 and not self.synchronize_protection(intent, remote_order, now=now):
                return False
            positions = self.adapter.get_positions()
            remote_position = next((position for position in positions if position.symbol == remote_order.symbol), None)
            local_quantity = self.ledger.filled_quantity(remote_order.client_order_id)
            if remote_position is None or remote_position.quantity != local_quantity:
                raise RuntimeError("position reconciliation mismatch")
            self.ledger.record_reconciliation(remote_order.symbol, status="MATCH", details={"client_order_id": remote_order.client_order_id, "filled_quantity": local_quantity}, event_time=now)
            self.recovery_state = self.ledger.recovery_state
            return self.recovery_state == "READY"
        except (TimeoutError, ConnectionError, KeyError, RuntimeError, ValueError):
            self.ledger.record_reconciliation(intent.symbol, status="UNKNOWN", details={"client_order_id": order_id, "reason": "RECOVERY_UNCONFIRMED"}, event_time=now)
            self.recovery_state = "RECOVERY"
            return False

    def reconcile(self, expected: PositionSnapshot | None = None) -> ReconciliationResult:
        result = self.adapter.reconcile(expected)
        symbol = expected.symbol if expected else (result.actual.symbol if result.actual else "UNKNOWN")
        if symbol is not None:
            self.ledger.record_reconciliation(symbol, status=result.status, details={"discrepancies": [item.value if isinstance(item, Enum) else item for item in result.discrepancies], "expected": expected.to_dict() if expected else None, "actual": result.actual.to_dict() if result.actual else None}, event_time=0.0)
        self.recovery_state = self.ledger.recovery_state
        return result

    def submit_order_request(self, order: OrderRequest, *, now: float = 0.0) -> ExecutionOutcome:
        """Submit a derived protection/order request through the same safety gate."""
        if not order.reduce_only:
            return ExecutionOutcome("REJECTED", reason="DIRECT_ENTRY_REQUIRES_INTENT")
        if not order.reduce_only and not self._check_recovery_gate(symbol=order.symbol, now=now):
            return ExecutionOutcome("REJECTED", reason="RECOVERY_REQUIRED")
        if not self.config.allows_submission(self.adapter.exchange, order.symbol):
            return ExecutionOutcome("REJECTED", reason="EXECUTION_MODE_DISABLED")
        if not order.reduce_only and (self.ledger.kill_switch_state == "KILLED" or self.config.global_kill_switch or self.config.exchange_kill_switch or order.symbol.upper() in self.config.symbol_kill_switches):
            return ExecutionOutcome("REJECTED", reason="KILL_SWITCH")
        if order.leverage > self.config.max_leverage or order.quantity <= 0:
            return ExecutionOutcome("REJECTED", reason="INVALID_ORDER")
        if order.client_order_id in self._requests:
            existing = self.adapter.get_order(order.client_order_id)
            return ExecutionOutcome("DUPLICATE", existing, "DUPLICATE_ORDER")
        if not self.adapter.health_check():
            return ExecutionOutcome("REJECTED", reason="EXCHANGE_UNAVAILABLE")
        self._requests[order.client_order_id] = str(order.to_dict())
        self.ledger.persist_order(order)
        try:
            submitted = self.adapter.submit_order(order)
        except (TimeoutError, ConnectionError, ExecutionTransportError, ValueError) as error:
            self.last_transport_error = error if isinstance(error, ExecutionTransportError) else None
            try:
                existing = self.adapter.get_order(order.client_order_id)
            except (TimeoutError, ConnectionError, ExecutionTransportError):
                existing = None
            if existing:
                return ExecutionOutcome("RECONCILED", existing, "SUBMISSION_RECONCILED")
            self.ledger.record_reconciliation(order.symbol, status="UNKNOWN", details={"client_order_id": order.client_order_id, "reason": "SUBMISSION_STATUS_UNKNOWN"}, event_time=now)
            self.recovery_state = "RECOVERY"
            return ExecutionOutcome("UNKNOWN", reason="SUBMISSION_STATUS_UNKNOWN")
        self.ledger.persist_order(submitted)
        if submitted.status is OrderStatus.REJECTED:
            self.ledger.record("ORDER_REJECTED", client_order_id=order.client_order_id, event_time=now)
            return ExecutionOutcome("REJECTED", submitted, "PROTECTION_REJECTED")
        if submitted.status is OrderStatus.UNKNOWN:
            self.ledger.record_reconciliation(order.symbol, status="UNKNOWN", details={"client_order_id": order.client_order_id, "reason": "PROTECTION_REJECTED"}, event_time=now)
            self.recovery_state = "RECOVERY"
            return ExecutionOutcome("UNKNOWN", submitted, "PROTECTION_REJECTED")
        return ExecutionOutcome("SUBMITTED", submitted)
