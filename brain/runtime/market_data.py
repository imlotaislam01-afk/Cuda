from __future__ import annotations

import asyncio
from typing import Any


class MarketDataManager:
    """Own one feed task and expose fail-closed readiness to the runtime."""

    def __init__(self, feed: Any) -> None:
        self.feed = feed
        self.running = False
        self.failed = False
        self.failure: BaseException | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        self.failed = False
        self.failure = None
        self._task = asyncio.create_task(self._run(), name="apex-market-data")
        return True

    async def _run(self) -> None:
        try:
            await self.feed.run()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self.failed = True
            self.failure = exc
        finally:
            self.running = False

    @property
    def ready(self) -> bool:
        data = getattr(self.feed, "data", None)
        if self.failed or not self.running or data is None:
            return False
        quality = getattr(data, "quality", None)
        if not callable(quality):
            return False
        status, _ = quality()
        return status == "DATA_VALID" and getattr(data, "continuity_status", "") == "HEALTHY"

    async def stop(self) -> bool:
        task = self._task
        if task is None:
            self.running = False
            return True
        self.running = False
        stop = getattr(self.feed, "stop", None)
        if callable(stop):
            stop()
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        return True