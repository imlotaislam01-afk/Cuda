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
        self.shutdown_task: asyncio.Task | None = None

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
                self.shutdown_task = loop.create_task(self._run_callback(callback), name="apex-shutdown")

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

    async def _run_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        try:
            await callback()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.failed = True
        finally:
            self.shutdown_task = None

    async def wait_for_signal_shutdown(self) -> bool:
        task = self.shutdown_task
        if task is not None:
            await task
        return not self.failed

    def remove_signal_handlers(self) -> None:
        for loop, event in self._signal_handlers:
            loop.remove_signal_handler(event)
        self._signal_handlers.clear()