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