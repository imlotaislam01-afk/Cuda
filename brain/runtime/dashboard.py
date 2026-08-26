from __future__ import annotations

import asyncio
from threading import Thread
from typing import Any


class DashboardManager:
    """Own authenticated dashboard servers and close them as one subsystem."""

    def __init__(self, http_server: Any, websocket_server: Any | None = None) -> None:
        self.http_server = http_server
        self.websocket_server = websocket_server
        self.thread: Thread | None = None
        self.running = False
        self.failed = False
        self.failure: BaseException | None = None

    async def start(self) -> bool:
        if self.running:
            return False
        try:
            self.thread = Thread(target=self.http_server.serve_forever, name="apex-dashboard-http")
            self.thread.start()
            if self.websocket_server is not None:
                await self.websocket_server.start()
            self.running = True
            self.failed = False
            self.failure = None
            return True
        except BaseException as exc:
            self.failed = True
            self.failure = exc
            await self.stop()
            return False

    @property
    def ready(self) -> bool:
        return self.running and not self.failed and self.thread is not None and self.thread.is_alive()

    async def stop(self) -> bool:
        self.running = False
        if self.websocket_server is not None:
            await self.websocket_server.close()
        if self.http_server is not None:
            self.http_server.shutdown()
            self.http_server.server_close()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.thread = None
        return True