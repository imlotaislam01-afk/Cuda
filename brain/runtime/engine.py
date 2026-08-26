from __future__ import annotations

from brain.execution import (
    ExecutionConfig,
    ExecutionCoordinator,
    ExecutionLedger,
    ExecutionMode,
    PaperExecutionAdapter,
)

from config.runtime import RuntimeConfig, RuntimeMode

from .health import RuntimeHealth
from .lifecycle import LifecycleState
from .recovery import RecoveryManager


class EngineSupervisor:
    """Authoritative owner for the application lifecycle and safety gates."""

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        *,
        ledger: ExecutionLedger | None = None,
        coordinator: ExecutionCoordinator | None = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self.state = LifecycleState.STARTING
        self.health = RuntimeHealth()
        self.ledger = ledger or ExecutionLedger(self.config.state_db_path)
        self.coordinator = coordinator or self._build_coordinator()
        self.recovery_manager = RecoveryManager(self.ledger, self.coordinator.adapter)
        self._record_lifecycle("RUNTIME_START", {"mode": str(self.config.mode)})

    def _build_coordinator(self) -> ExecutionCoordinator:
        if getattr(self.config.mode, "value", self.config.mode) != RuntimeMode.PAPER.value:
            raise ValueError("Stage 23 supervisor only permits PAPER mode")
        execution_config = ExecutionConfig(
            mode=ExecutionMode.PAPER,
            exchange="PAPER",
            state_db_path=self.config.state_db_path,
            max_position_notional=self.config.max_position_notional_usd,
            max_leverage=self.config.leverage,
        )
        return ExecutionCoordinator(PaperExecutionAdapter(), execution_config, self.ledger)

    def _record_lifecycle(self, event_type: str, details: dict[str, str] | None = None) -> None:
        if self.ledger is None:
            return
        self.ledger.record(event_type, event_time=0.0, **(details or {}))

    def start(self) -> bool:
        if self.state in {LifecycleState.READY, LifecycleState.RUNNING}:
            return False
        if self.state is LifecycleState.STOPPING:
            return False
        self.state = LifecycleState.RECOVERING
        self.health.lifecycle_state = self.state
        self._record_lifecycle("RUNTIME_RECOVERY", {"state": self.state.value})
        if not self.ledger.integrity_check() or not self.recovery_manager.recover():
            self.state = LifecycleState.DEGRADED
            self.health.lifecycle_state = self.state
            self.health.reconciliation_ok = False
            self.health.exchange_ok = False
            self.health.account_ok = False
            self._record_lifecycle("RUNTIME_DEGRADED", {"state": self.state.value})
            return False
        self.state = LifecycleState.READY
        self.health.lifecycle_state = self.state
        self._record_lifecycle("RUNTIME_READY", {"state": self.state.value})
        self.state = LifecycleState.RUNNING
        self.health.lifecycle_state = self.state
        self._record_lifecycle("RUNTIME_RUNNING", {"state": self.state.value})
        return True

    def stop(self) -> bool:
        if self.state is LifecycleState.STOPPED:
            return True
        self.state = LifecycleState.STOPPING
        self.health.lifecycle_state = self.state
        self._record_lifecycle("RUNTIME_STOPPING", {"state": self.state.value})
        self.coordinator.recovery_state = "RECOVERY"
        self.ledger.record_recovery_event("RECOVERY", "runtime stopped", payload={}, event_time=0.0)
        self.state = LifecycleState.STOPPED
        self.health.lifecycle_state = self.state
        self._record_lifecycle("RUNTIME_STOPPED", {"state": self.state.value})
        self.ledger.close()
        return True

    @property
    def execution_allowed(self) -> bool:
        return self.state is LifecycleState.RUNNING and self.health.execution_ready