import asyncio

from brain.runtime.brain_loop import BrainLoop


class Context:
    symbol = "BTCUSDT"
    event_time = 100.0


class Pipeline:
    def __init__(self, failure=False):
        self.calls = 0
        self.failure = failure

    def run(self, context):
        self.calls += 1
        if self.failure:
            raise RuntimeError("brain failed")
        return context


def test_brain_loop_deduplicates_and_rejects_stale_contexts():
    async def scenario():
        pipeline = Pipeline()
        loop = BrainLoop(pipeline, stale_after=5, clock=lambda: 100)
        assert await loop.start() is True
        assert await loop.submit(Context()) is True
        assert await loop.submit(Context()) is False
        assert await loop.stop() is True
        assert pipeline.calls == 1

    asyncio.run(scenario())


def test_brain_loop_isolates_pipeline_errors():
    async def scenario():
        loop = BrainLoop(Pipeline(failure=True), clock=lambda: 100)
        await loop.start()
        assert await loop.submit(Context()) is True
        await loop.queue.join()
        assert loop.failed is True
        assert loop.last_error is not None
        assert loop.running is False
        assert await loop.submit(Context()) is False
        await loop.stop()

    asyncio.run(scenario())