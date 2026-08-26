from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable


class ShutdownManager:
    """Bounded signal-driven shutdown admission gate."""

    def __init__(self) -> None:
        self.accepting_work = True
        self.requested = False
        self.completed = False
        self.failed = False
        self._signal_handlers: list[tuple[asyncio.AbstractEventLoop, signal.Signals]] = []

    def begin(self) -> bool:
        if not self.accepting_work:
            return False
        self.accepting_work = False
        self.requested = True
        return True

    def install_signal_handlers(self, callback: Callable[[], Awaitable[None]]) -> None:
        loop = asyncio.get_running_loop()

        def request() -> None:
            if self.begin():
                loop.create_task(callback(), name="apex-shutdown")

        for event in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(event, request)
            self._signal_handlers.append((loop, event))

    async def run(self, steps: list[Callable[[], Awaitable[None]]], *, timeout: float = 10.0) -> bool:
        if timeout <= 0:
            raise ValueError("Shutdown timeout must be positive")
        if self.completed:
            return True
        if not self.requested:
            self.begin()
        try:
            async with asyncio.timeout(timeout):
                for step in steps:
                    await step()
        except (TimeoutError, asyncio.CancelledError):
            self.failed = True
            return False
        finally:
            for loop, event in self._signal_handlers:
                loop.remove_signal_handler(event)
            self._signal_handlers.clear()
        self.completed = True
        return True