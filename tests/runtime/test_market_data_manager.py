import asyncio
from types import SimpleNamespace

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


def test_market_data_manager_keeps_single_owned_task_and_tracks_state():
    async def scenario():
        manager = MarketDataManager(FakeFeed())
        assert manager.state.value == "CREATED"
        assert await manager.start() is True
        assert await manager.start() is False
        assert manager._task is not None
        assert manager.state.value in {"STARTING", "CONNECTING", "CONNECTED", "READY", "RUNNING"}
        await manager.stop()
        assert manager._task is None
        assert manager.state.value == "STOPPED"

    asyncio.run(scenario())


def test_supervisor_blocks_brain_processing_when_market_data_is_unhealthy():
    async def scenario():
        from brain.runtime.engine import EngineSupervisor
        from brain.runtime.lifecycle import LifecycleState
        from config.runtime import RuntimeConfig

        class StaleFeed:
            def __init__(self):
                self.data = SimpleNamespace(
                    quality=lambda **kwargs: ("DATA_STALE", "stale"),
                    continuity_status="HEALTHY",
                )
                self.running = False

            async def run(self):
                self.running = True
                try:
                    while self.running:
                        await asyncio.sleep(0.01)
                finally:
                    self.running = False

            def stop(self):
                self.running = False

        stale_feed = StaleFeed()
        market = MarketDataManager(stale_feed)
        market.running = True
        market.state = market.state.__class__.STALE

        async def should_not_run(_context):
            raise AssertionError("brain must not process stale market data")

        supervisor = EngineSupervisor(
            config=RuntimeConfig(),
            market_data=market,
            brain_loop=SimpleNamespace(submit=should_not_run, result_handler=None),
            execution_consumer=SimpleNamespace(start=lambda: True, stop=lambda: True, ready=True, running=False),
            reconciliation_service=SimpleNamespace(start=lambda: True, stop=lambda: True, ready=True, running=False, reconcile_once=lambda: True),
        )

        supervisor.state = LifecycleState.RUNNING
        supervisor.health.market_data_ok = False
        assert market.ready is False

    asyncio.run(scenario())