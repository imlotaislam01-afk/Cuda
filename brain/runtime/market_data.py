from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any


class MarketDataState(str, Enum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    READY = "READY"
    RUNNING = "RUNNING"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class MarketDataManager:
    """Own one feed task and expose fail-closed readiness to the runtime."""

    def __init__(self, feed: Any) -> None:
        self.feed = feed
        self.running = False
        self.failed = False
        self.failure: BaseException | None = None
        self.state = MarketDataState.CREATED
        self._task: asyncio.Task | None = None

    async def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        self.failed = False
        self.failure = None
        self.state = MarketDataState.STARTING
        self._task = asyncio.create_task(self._run(), name="apex-market-data")
        return True

    async def _run(self) -> None:
        try:
            self.state = MarketDataState.CONNECTING
            await self.feed.run()
        except asyncio.CancelledError:
            self.state = MarketDataState.STOPPED
            raise
        except BaseException as exc:
            self.failed = True
            self.failure = exc
            self.state = MarketDataState.DEGRADED
        finally:
            self.running = False
            if self.state not in {MarketDataState.STOPPED, MarketDataState.STOPPING}:
                self.state = MarketDataState.DISCONNECTED if self.failure is not None else MarketDataState.STOPPED

    def _evaluate_health(self) -> tuple[bool, MarketDataState]:
        data = getattr(self.feed, "data", None)
        if self.failed or not self.running or data is None:
            return False, MarketDataState.DISCONNECTED
        quality = getattr(data, "quality", None)
        if not callable(quality):
            return False, MarketDataState.DEGRADED
        status, reason = quality()
        if status == "DATA_STALE":
            return False, MarketDataState.STALE
        if status in {"DATA_INVALID", "DATA_INCOMPLETE"}:
            return False, MarketDataState.DEGRADED
        continuity = getattr(data, "continuity_status", "")
        if continuity in {"DISCONNECTED", "RECONNECTING", "SEQUENCE_GAP", "OUT_OF_ORDER"}:
            return False, MarketDataState.DISCONNECTED
        if status == "DATA_VALID" and continuity == "HEALTHY":
            return True, MarketDataState.RUNNING
        return False, MarketDataState.CONNECTING

    @property
    def ready(self) -> bool:
        ready, state = self._evaluate_health()
        self.state = state
        return ready

    async def stop(self) -> bool:
        task = self._task
        self.state = MarketDataState.STOPPING
        self.running = False
        stop = getattr(self.feed, "stop", None)
        if callable(stop):
            stop()
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        self.failed = False
        self.failure = None
        self.state = MarketDataState.STOPPED
        return True