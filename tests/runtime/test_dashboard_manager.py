import asyncio

from brain.dashboard import create_http_server
from brain.execution import ExecutionCoordinator, PaperExecutionAdapter
from brain.runtime.dashboard import DashboardManager
from tests.dashboard.test_service import result


def test_dashboard_manager_owns_authenticated_http_lifecycle():
    async def scenario():
        server = create_http_server(lambda: result(), token="test-token")
        manager = DashboardManager(server)
        assert await manager.start() is True
        assert manager.ready is True
        assert await manager.stop() is True
        assert manager.ready is False
        assert await manager.stop() is True

    asyncio.run(scenario())


def test_dashboard_thread_failure_isolated_from_execution_state():
    async def scenario():
        class BrokenHTTPServer:
            def serve_forever(self):
                raise OSError("dashboard thread failed")

            def shutdown(self):
                return None

            def server_close(self):
                return None

        coordinator = ExecutionCoordinator(PaperExecutionAdapter())
        manager = DashboardManager(BrokenHTTPServer())
        assert await manager.start() is True
        await asyncio.to_thread(manager.thread.join, 1.0)
        assert manager.failed is True
        assert isinstance(manager.failure, OSError)
        assert manager.ready is False
        assert coordinator.recovery_state == "READY"
        await manager.stop()

    asyncio.run(scenario())