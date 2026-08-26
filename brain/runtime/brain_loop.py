from __future__ import annotations

import asyncio
import time
from typing import Any, Callable


class BrainLoop:
    """Bounded canonical-context consumer that never submits exchange orders."""

    def __init__(self, pipeline: Any, *, max_queue_size: int = 64, max_results: int = 1000, stale_after: float = 30.0,
                 clock: Callable[[], float] | None = None) -> None:
        if max_queue_size <= 0 or max_results <= 0 or stale_after < 0:
            raise ValueError("Brain loop limits must be positive")
        self.pipeline = pipeline
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)
        self.max_results = max_results
        self.stale_after = stale_after
        self.clock = clock or time.time
        self.running = False
        self.failed = False
        self.last_error: BaseException | None = None
        self.results: list[Any] = []
        self._seen: set[tuple[str, float]] = set()
        self._task: asyncio.Task | None = None

    async def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        self.failed = False
        self.last_error = None
        self._task = asyncio.create_task(self._consume(), name="apex-brain-loop")
        return True

    async def submit(self, context: Any) -> bool:
        if not self.running:
            return False
        event_time = getattr(context, "event_time", None)
        symbol = str(getattr(context, "symbol", "")).upper()
        if not symbol or event_time is None:
            return False
        key = (symbol, float(event_time))
        if key in self._seen:
            return False
        if self.clock() - float(event_time) > self.stale_after:
            return False
        self._seen.add(key)
        try:
            self.queue.put_nowait(context)
        except asyncio.QueueFull:
            self._seen.discard(key)
            return False
        return True

    async def _consume(self) -> None:
        while self.running:
            context = await self.queue.get()
            try:
                self.results.append(self.pipeline.run(context))
                if len(self.results) > self.max_results:
                    del self.results[:-self.max_results]
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
        task = self._task
        if task is None:
            self.running = False
            return True
        await self.queue.join()
        self.running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        return True