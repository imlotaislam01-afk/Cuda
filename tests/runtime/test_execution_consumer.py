import asyncio

from brain.execution import ExecutionOutcome
from brain.runtime.execution_consumer import ExecutionConsumer
from tests.execution.test_p3_foundation import intent


class Coordinator:
    def __init__(self):
        self.calls = 0

    def submit_intent(self, value, **kwargs):
        self.calls += 1
        return ExecutionOutcome("UNKNOWN" if self.calls == 1 else "SUBMITTED")


class FailingCoordinator:
    def submit_intent(self, value, **kwargs):
        raise RuntimeError("submission worker failed")


def test_execution_consumer_deduplicates_and_does_not_retry_unknown():
    async def scenario():
        coordinator = Coordinator()
        consumer = ExecutionConsumer(coordinator)
        await consumer.start()
        value = intent()
        assert await consumer.submit(value) is True
        assert await consumer.submit(value) is False
        await consumer.queue.join()
        assert [outcome.status for outcome in consumer.outcomes] == ["UNKNOWN"]
        await consumer.stop()
        assert coordinator.calls == 1

    asyncio.run(scenario())


def test_execution_consumer_records_worker_failure_and_stops_admission():
    async def scenario():
        consumer = ExecutionConsumer(FailingCoordinator())
        await consumer.start()
        assert await consumer.submit(intent()) is True
        await consumer.queue.join()
        assert consumer.failed is True
        assert isinstance(consumer.last_error, RuntimeError)
        assert consumer.running is False
        assert await consumer.submit(intent()) is False
        await consumer.stop()

    asyncio.run(scenario())