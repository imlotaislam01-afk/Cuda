from __future__ import annotations

import asyncio
from typing import Any, Callable


class ReconciliationService:
    """Own recurring remote reconciliation and expose fail-closed health."""

    def __init__(self, coordinator: Any, *, interval_seconds: float = 30.0,
                 clock: Callable[[], float] | None = None) -> None:
        if interval_seconds <= 0:
            raise ValueError("Reconciliation interval must be positive")
        self.coordinator = coordinator
        self.interval_seconds = interval_seconds
        self.clock = clock
        self.running = False
        self.healthy = False
        self.last_error: BaseException | None = None
        self.last_result: Any | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        self.healthy = False
        self.last_error = None
        self._task = asyncio.create_task(self._run(), name="apex-reconciliation")
        return True

    async def reconcile_once(self) -> bool:
        try:
            if not self.coordinator.adapter.health_check():
                raise ConnectionError("exchange health check failed")
            positions = self.coordinator.adapter.get_positions()
            if positions is None:
                raise RuntimeError("remote positions unavailable")
            if not positions:
                result = self.coordinator.reconcile()
                self.last_result = result
                self.healthy = result.status in {"MATCH", "OK"}
                return self.healthy
            results = [self.coordinator.reconcile(position) for position in positions]
            self.last_result = results[-1]
            self.healthy = all(result.status in {"MATCH", "OK"} for result in results)
            if not self.healthy:
                self.coordinator.recovery_state = "RECOVERY"
            return self.healthy
        except (TimeoutError, ConnectionError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            self.last_error = exc
            self.healthy = False
            self.coordinator.recovery_state = "RECOVERY"
            self.coordinator.ledger.record_reconciliation(
                "UNKNOWN",
                status="UNKNOWN",
                details={"reason": "RECONCILIATION_FAILED", "error": type(exc).__name__},
                event_time=0.0,
            )
            return False

    async def _run(self) -> None:
        while self.running:
            await self.reconcile_once()
            await asyncio.sleep(self.interval_seconds)

    async def stop(self) -> bool:
        if self._task is None:
            self.running = False
            return True
        self.running = False
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        return True