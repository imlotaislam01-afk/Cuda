from __future__ import annotations

import asyncio
import inspect
from typing import Any

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
        market_data: Any | None = None,
        brain_loop: Any | None = None,
        execution_consumer: Any | None = None,
        reconciliation_service: Any | None = None,
        dashboard: Any | None = None,
        shutdown_manager: Any | None = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self.state = LifecycleState.STARTING
        self.health = RuntimeHealth()
        self.ledger = ledger or ExecutionLedger(self.config.state_db_path)
        self.coordinator = coordinator or self._build_coordinator()
        self.recovery_manager = RecoveryManager(self.ledger, self.coordinator.adapter)
        self.market_data = market_data
        self.brain_loop = brain_loop
        self.execution_consumer = execution_consumer
        self.reconciliation_service = reconciliation_service
        self.dashboard = dashboard
        self.shutdown_manager = shutdown_manager
        self._runtime_components = (
            ("market_data", self.market_data),
            ("brain", self.brain_loop),
            ("execution", self.execution_consumer),
            ("reconciliation", self.reconciliation_service),
            ("dashboard", self.dashboard),
        )
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

    def start(self, *, activate: bool = True) -> bool:
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
        if not activate:
            return True
        self.state = LifecycleState.RUNNING
        self.health.lifecycle_state = self.state
        self._record_lifecycle("RUNTIME_RUNNING", {"state": self.state.value})
        return True

    @staticmethod
    def _component_ready(component: Any) -> bool:
        ready = getattr(component, "ready", None)
        return ready is None or bool(ready)

    async def start_runtime(self) -> bool:
        """Start all injected runtime subsystems under one lifecycle owner."""
        if not self.start(activate=False):
            return False
        if self.brain_loop is not None and self.execution_consumer is not None and hasattr(self.brain_loop, "result_handler"):
            async def handle_result(result: Any) -> None:
                intent = getattr(result, "intent", None)
                if intent is not None:
                    await self.execution_consumer.submit(intent, as_of=getattr(result.context, "event_time", None), now=0.0)
            self.brain_loop.result_handler = handle_result
        started: list[Any] = []
        try:
            for name, component in self._runtime_components:
                if component is None:
                    continue
                if not await component.start():
                    raise RuntimeError(f"{name} failed to start")
                started.append(component)
                if not self._component_ready(component):
                    raise RuntimeError(f"{name} is not ready")
            self.state = LifecycleState.RUNNING
            self.health.lifecycle_state = self.state
            self._record_lifecycle("RUNTIME_RUNNING", {"state": self.state.value})
            if self.shutdown_manager is not None:
                self.shutdown_manager.install_signal_handlers(self.stop_runtime)
            self._record_lifecycle("RUNTIME_COMPONENTS_READY", {"state": self.state.value})
            return True
        except Exception as exc:
            for component in reversed(started):
                try:
                    await component.stop()
                except Exception:
                    pass
            self.health.execution_ok = False
            self.state = LifecycleState.DEGRADED
            self.health.lifecycle_state = self.state
            self._record_lifecycle("RUNTIME_DEGRADED", {"reason": type(exc).__name__})
            return False

    def _component_failed(self, component: Any) -> bool:
        return bool(getattr(component, "failed", False))

    async def run_forever(self, context_provider: Any, *, poll_interval: float = 0.1) -> bool:
        """Run the supervised context-to-intent loop until stopped or degraded."""
        if poll_interval <= 0:
            raise ValueError("Runtime poll interval must be positive")
        if not await self.start_runtime():
            return False
        try:
            while self.state is LifecycleState.RUNNING:
                if any(self._component_failed(component) for _name, component in self._runtime_components if component is not None):
                    self.health.execution_ok = False
                    self.state = LifecycleState.DEGRADED
                    self.health.lifecycle_state = self.state
                    self._record_lifecycle("RUNTIME_DEGRADED", {"reason": "COMPONENT_FAILURE"})
                    break
                context = context_provider()
                if inspect.isawaitable(context):
                    context = await context
                if context is not None and self.brain_loop is not None:
                    await self.brain_loop.submit(context)
                await asyncio.sleep(poll_interval)
        finally:
            await self.stop_runtime()
        return True

    async def stop_runtime(self) -> bool:
        """Stop owned runtime subsystems in reverse dependency order."""
        if self.state is LifecycleState.STOPPED:
            return True
        self.state = LifecycleState.STOPPING
        self.health.lifecycle_state = self.state
        self._record_lifecycle("RUNTIME_STOPPING", {"state": self.state.value})
        for _name, component in reversed(self._runtime_components):
            if component is None:
                continue
            try:
                await component.stop()
            except Exception:
                self.health.execution_ok = False
        if self.shutdown_manager is not None:
            self.shutdown_manager.remove_signal_handlers()
        self.coordinator.recovery_state = "RECOVERY"
        self.ledger.record_recovery_event("RECOVERY", "runtime stopped", payload={}, event_time=0.0)
        self.state = LifecycleState.STOPPED
        self.health.lifecycle_state = self.state
        self._record_lifecycle("RUNTIME_STOPPED", {"state": self.state.value})
        self.ledger.close()
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