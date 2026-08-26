import asyncio

from brain.runtime.market_data import MarketDataManager


class FakeFeed:
    def __init__(self, failure=None):
        self.failure = failure
        self.stopped = False

    async def run(self):
        if self.failure:
            raise self.failure
        while not self.stopped:
            await asyncio.sleep(0)

    def stop(self):
        self.stopped = True


def test_market_data_manager_owns_and_cancels_feed_task():
    async def scenario():
        manager = MarketDataManager(FakeFeed())
        assert await manager.start() is True
        assert manager.running is True
        assert await manager.stop() is True
        assert manager.running is False
        assert await manager.stop() is True

    asyncio.run(scenario())


def test_market_data_manager_failures_are_not_ready():
    async def scenario():
        manager = MarketDataManager(FakeFeed(RuntimeError("feed failed")))
        assert await manager.start() is True
        await manager._task
        assert manager.failed is True
        assert manager.ready is False

    asyncio.run(scenario())