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
        self.recovery_manager = RecoveryManager(self.ledger)
        self.coordinator = coordinator or self._build_coordinator()

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

    def start(self) -> bool:
        if self.state in {LifecycleState.READY, LifecycleState.RUNNING}:
            return False
        if self.state is LifecycleState.STOPPING:
            return False
        self.state = LifecycleState.RECOVERING
        self.health.lifecycle_state = self.state
        if not self.ledger.integrity_check() or not self.recovery_manager.recover():
            self.state = LifecycleState.DEGRADED
            self.health.lifecycle_state = self.state
            self.health.reconciliation_ok = False
            return False
        self.state = LifecycleState.READY
        self.health.lifecycle_state = self.state
        self.state = LifecycleState.RUNNING
        self.health.lifecycle_state = self.state
        return True

    def stop(self) -> bool:
        if self.state is LifecycleState.STOPPED:
            return True
        self.state = LifecycleState.STOPPING
        self.health.lifecycle_state = self.state
        self.coordinator.recovery_state = "RECOVERY"
        self.ledger.record_recovery_event("RECOVERY", "runtime stopped", payload={}, event_time=0.0)
        self.ledger.close()
        self.state = LifecycleState.STOPPED
        self.health.lifecycle_state = self.state
        return True

    @property
    def execution_allowed(self) -> bool:
        return self.state is LifecycleState.RUNNING and self.health.execution_ready