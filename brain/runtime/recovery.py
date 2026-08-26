from __future__ import annotations

from brain.execution import ExecutionLedger


class RecoveryManager:
    def __init__(self, ledger: ExecutionLedger | None = None) -> None:
        self.ledger = ledger or ExecutionLedger()

    def is_recovery_required(self) -> bool:
        if self.ledger is None:
            return False
        state = self.ledger.recovery_state
        return state == "RECOVERY"

    def recover(self) -> bool:
        if self.is_recovery_required():
            self.ledger.record_recovery_event("RECOVERING", "runtime recovery", payload={"source": "engine"}, event_time=0.0)
            return False
        return True
