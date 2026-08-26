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


def test_signal_shutdown_task_is_owned_and_awaitable():
    async def scenario():
        manager = ShutdownManager()
        handlers = {}
        loop = asyncio.get_running_loop()
        original = loop.add_signal_handler
        loop.add_signal_handler = lambda event, callback: handlers.__setitem__(event, callback)
        try:
            async def callback():
                await asyncio.sleep(0)

            manager.install_signal_handlers(callback)
            handlers[next(iter(handlers))]()
            assert await manager.wait_for_signal_shutdown() is True
            assert manager.shutdown_task is None
            assert manager.requested is True
        finally:
            loop.add_signal_handler = original
            for event in tuple(handlers):
                loop.remove_signal_handler(event)

    asyncio.run(scenario())