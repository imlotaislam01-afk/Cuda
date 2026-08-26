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


def test_execution_consumer_persists_intent_before_queue_admission(tmp_path):
    async def scenario():
        from brain.execution import ExecutionLedger

        ledger = ExecutionLedger(str(tmp_path / "intent.sqlite3"))
        consumer = ExecutionConsumer(Coordinator(), ledger=ledger)
        await consumer.start()
        value = intent()

        assert await consumer.submit(value) is True
        client_order_id = consumer._client_order_id(value)
        persisted = ledger.load_intent(client_order_id)
        assert persisted is not None
        assert persisted.status == "QUEUED"
        await consumer.stop()

    asyncio.run(scenario())


def test_execution_consumer_recovers_persisted_intent_after_restart(tmp_path):
    async def scenario():
        from brain.execution import ExecutionLedger

        path = str(tmp_path / "restart.sqlite3")
        ledger = ExecutionLedger(path)
        first = ExecutionConsumer(Coordinator(), ledger=ledger)
        await first.start()
        value = intent()
        assert await first.submit(value) is True
        first._task.cancel()
        try:
            await first._task
        except asyncio.CancelledError:
            pass
        first.running = False
        first._task = None
        ledger.close()

        recovered_ledger = ExecutionLedger(path)
        coordinator = Coordinator()
        second = ExecutionConsumer(coordinator, ledger=recovered_ledger)
        assert await second.start() is True
        await second.queue.join()
        assert coordinator.calls == 1
        await second.stop()

    asyncio.run(scenario())


def test_execution_consumer_does_not_recover_rejected_expired_or_unknown_intents(tmp_path):
    async def scenario():
        from brain.execution import ExecutionLedger

        path = str(tmp_path / "terminal.sqlite3")
        ledger = ExecutionLedger(path)
        value = intent()
        client_order_id = "rejected"
        ledger.persist_intent(value, client_order_id=client_order_id, status="REJECTED", created_at=1.0)
        ledger.persist_intent(value, client_order_id="expired", status="QUEUED", created_at=1.0)
        ledger.persist_intent(value, client_order_id="unknown", status="UNKNOWN", created_at=1.0)
        ledger.close()

        recovered = ExecutionLedger(path)
        consumer = ExecutionConsumer(Coordinator(), ledger=recovered, clock=lambda: 100.0)
        consumer.coordinator.config = type("Config", (), {"stale_intent_after": 10.0})()
        await consumer.start()
        await consumer.queue.join()
        assert consumer.queue.empty()
        assert recovered.load_intent("expired").status == "EXPIRED"
        assert recovered.load_intent("unknown").status == "UNKNOWN"
        await consumer.stop()

    asyncio.run(scenario())


def test_execution_consumer_marks_malformed_persisted_intent_failed(tmp_path):
    async def scenario():
        from brain.execution import ExecutionLedger

        ledger = ExecutionLedger(str(tmp_path / "malformed.sqlite3"))
        ledger._connection.execute(
            "INSERT INTO execution_intents (client_order_id, symbol, status, created_at, payload_json) VALUES (?, ?, ?, ?, ?)",
            ("malformed", "BTCUSDT", "QUEUED", 1.0, "{bad-json"),
        )
        ledger._connection.commit()
        consumer = ExecutionConsumer(Coordinator(), ledger=ledger)
        await consumer.start()
        assert ledger.load_intent("malformed").status == "FAILED"
        await consumer.stop()

    asyncio.run(scenario())


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