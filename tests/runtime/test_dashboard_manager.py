import asyncio

from brain.dashboard import create_http_server
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