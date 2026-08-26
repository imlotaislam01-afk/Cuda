from __future__ import annotations

from brain.execution import ExecutionLedger


class RecoveryManager:
    def __init__(self, ledger: ExecutionLedger | None = None, adapter=None) -> None:
        self.ledger = ledger or ExecutionLedger()
        self.adapter = adapter
        self.last_error: str | None = None

    def is_recovery_required(self) -> bool:
        if self.ledger is None:
            return False
        state = self.ledger.recovery_state
        return state == "RECOVERY"

    def recover(self) -> bool:
        self.last_error = None
        if self.is_recovery_required():
            self.ledger.record_recovery_event("RECOVERING", "runtime recovery", payload={"source": "engine"}, event_time=0.0)
            return False
        if self.adapter is None:
            return True
        try:
            if not self.adapter.health_check():
                raise RuntimeError("exchange health check failed")
            account = self.adapter.get_account_state()
            if not isinstance(account, dict) or account.get("healthy") is not True:
                raise RuntimeError("account state is not healthy")
            open_orders = self.adapter.get_open_orders()
            positions = self.adapter.get_positions()
            if open_orders is None or positions is None:
                raise RuntimeError("remote state is unavailable")
            for order in open_orders:
                self.ledger.persist_order(order)
            for position in positions:
                self.ledger.persist_position(position)
            for position in positions:
                result = self.adapter.reconcile(position)
                self.ledger.record_reconciliation(
                    position.symbol,
                    status=result.status,
                    details={"source": "startup", "discrepancies": list(result.discrepancies)},
                    event_time=0.0,
                )
                if result.status not in {"MATCH", "OK"}:
                    raise RuntimeError(f"position reconciliation failed for {position.symbol}")
        except Exception as exc:
            self.last_error = str(exc)
            self.ledger.record_recovery_event("RECOVERY", self.last_error, payload={"source": "exchange"}, event_time=0.0)
            return False
        return True
