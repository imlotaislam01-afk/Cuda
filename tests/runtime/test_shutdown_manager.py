import asyncio

from brain.runtime.shutdown import ShutdownManager


def test_shutdown_manager_runs_ordered_steps_once():
    async def scenario():
        manager = ShutdownManager()
        calls = []

        async def first():
            calls.append("stop-input")

        async def second():
            calls.append("persist")

        assert await manager.run([first, second]) is True
        assert calls == ["stop-input", "persist"]
        assert await manager.run([first]) is True

    asyncio.run(scenario())


def test_shutdown_manager_times_out_fail_closed():
    async def scenario():
        manager = ShutdownManager()

        async def blocked():
            await asyncio.sleep(1)

        assert await manager.run([blocked], timeout=0.001) is False
        assert manager.failed is True

    asyncio.run(scenario())