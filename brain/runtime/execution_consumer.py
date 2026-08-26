from __future__ import annotations

import asyncio
import time
from typing import Any

from brain.execution import ExecutionIntent, ExecutionOutcome, ExecutionLedger, OrderRequest


class ExecutionConsumer:
    """Single bounded queue consumer delegating all execution to the coordinator."""

    def __init__(self, coordinator: Any, *, ledger: ExecutionLedger | None = None, max_queue_size: int = 64,
                 clock: Any | None = None) -> None:
        if max_queue_size <= 0:
            raise ValueError("Execution queue size must be positive")
        self.coordinator = coordinator
        self.ledger = ledger or getattr(coordinator, "ledger", None)
        self.clock = clock or time.time
        self.queue: asyncio.Queue[tuple[Any, float | None, float]] = asyncio.Queue(maxsize=max_queue_size)
        self.running = False
        self.failed = False
        self.last_error: BaseException | None = None
        self._task: asyncio.Task | None = None
        self._seen: set[str] = set()
        self.outcomes: list[ExecutionOutcome] = []

    async def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        self.failed = False
        self.last_error = None
        self._recover_persisted_intents()
        self._task = asyncio.create_task(self._consume(), name="apex-execution-consumer")
        return True

    @staticmethod
    def _client_order_id(intent: Any) -> str:
        return OrderRequest.from_intent(intent).client_order_id

    def _recover_persisted_intents(self) -> None:
        if self.ledger is None:
            return
        recoverable = self.ledger.load_intents(("CREATED", "PERSISTED", "QUEUED", "RECOVERED", "PROCESSING", "APPROVED"))
        for state in recoverable:
            try:
                if self.ledger.load_order(state.client_order_id) is not None:
                    self.ledger.update_intent_status(state.client_order_id, "UNKNOWN")
                    continue
                intent = ExecutionIntent.from_dict(state.payload)
                if not intent.approved:
                    self.ledger.update_intent_status(state.client_order_id, "REJECTED")
                    continue
                stale_after = float(getattr(getattr(self.coordinator, "config", None), "stale_intent_after", 0.0))
                if state.created_at > 0 and stale_after > 0 and self.clock() - state.created_at > stale_after:
                    self.ledger.update_intent_status(state.client_order_id, "EXPIRED")
                    continue
                self.queue.put_nowait((intent, None, state.created_at))
                self._seen.add(state.client_order_id)
                self.ledger.update_intent_status(state.client_order_id, "RECOVERED")
            except (KeyError, TypeError, ValueError, asyncio.QueueFull):
                self.ledger.update_intent_status(state.client_order_id, "FAILED")

    async def submit(self, intent: Any, *, as_of: float | None = None, now: float = 0.0) -> bool:
        if not self.running or not getattr(intent, "approved", False):
            return False
        client_order_id = self._client_order_id(intent)
        if client_order_id in self._seen:
            return False
        if self.ledger is not None:
            self.ledger.persist_intent(intent, client_order_id=client_order_id, status="PERSISTED", created_at=now)
        try:
            self.queue.put_nowait((intent, as_of, now))
        except asyncio.QueueFull:
            return False
        self._seen.add(client_order_id)
        if self.ledger is not None:
            self.ledger.update_intent_status(client_order_id, "QUEUED")
        return True

    async def _consume(self) -> None:
        while self.running:
            intent, as_of, now = await self.queue.get()
            client_order_id = self._client_order_id(intent)
            try:
                if self.ledger is not None:
                    self.ledger.update_intent_status(client_order_id, "PROCESSING")
                self.outcomes.append(self.coordinator.submit_intent(intent, as_of=as_of, now=now))
                if self.ledger is not None:
                    status = self.outcomes[-1].status
                    self.ledger.update_intent_status(client_order_id, status)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.failed = True
                self.last_error = exc
                self.running = False
                return
            finally:
                self.queue.task_done()

    async def stop(self) -> bool:
        if self._task is None:
            self.running = False
            return True
        await self.queue.join()
        self.running = False
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        return True