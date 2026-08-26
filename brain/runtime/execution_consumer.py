from __future__ import annotations

import asyncio
from typing import Any

from brain.execution import ExecutionOutcome, OrderRequest


class ExecutionConsumer:
    """Single bounded queue consumer delegating all execution to the coordinator."""

    def __init__(self, coordinator: Any, *, max_queue_size: int = 64) -> None:
        if max_queue_size <= 0:
            raise ValueError("Execution queue size must be positive")
        self.coordinator = coordinator
        self.queue: asyncio.Queue[tuple[Any, float | None, float]] = asyncio.Queue(maxsize=max_queue_size)
        self.running = False
        self._task: asyncio.Task | None = None
        self._seen: set[str] = set()
        self.outcomes: list[ExecutionOutcome] = []

    async def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        self._task = asyncio.create_task(self._consume(), name="apex-execution-consumer")
        return True

    async def submit(self, intent: Any, *, as_of: float | None = None, now: float = 0.0) -> bool:
        if not self.running or not getattr(intent, "approved", False):
            return False
        client_order_id = OrderRequest.from_intent(intent).client_order_id
        if client_order_id in self._seen:
            return False
        try:
            self.queue.put_nowait((intent, as_of, now))
        except asyncio.QueueFull:
            return False
        self._seen.add(client_order_id)
        return True

    async def _consume(self) -> None:
        while self.running:
            intent, as_of, now = await self.queue.get()
            try:
                self.outcomes.append(self.coordinator.submit_intent(intent, as_of=as_of, now=now))
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