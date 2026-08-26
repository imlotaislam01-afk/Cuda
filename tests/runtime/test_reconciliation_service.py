import asyncio

from brain.execution import ExecutionConfig, ExecutionCoordinator, ExecutionLedger, OrderRequest, PaperExecutionAdapter
from brain.runtime.reconciliation_service import ReconciliationService
from tests.execution.test_p3_foundation import intent


def test_reconciliation_detects_local_order_missing_from_exchange(tmp_path):
    async def scenario():
        path = str(tmp_path / "orders.sqlite3")
        ledger = ExecutionLedger(path)
        coordinator = ExecutionCoordinator(PaperExecutionAdapter(), ExecutionConfig(state_db_path=path), ledger)
        order = OrderRequest.from_intent(intent())
        ledger.persist_order(order)
        service = ReconciliationService(coordinator)

        assert await service.reconcile_once() is False
        assert coordinator.recovery_state == "RECOVERY"

    asyncio.run(scenario())

from brain.execution import ExecutionCoordinator, PaperExecutionAdapter
from brain.runtime.reconciliation_service import ReconciliationService


def test_reconciliation_service_persists_a_matching_remote_result():
    async def scenario():
        coordinator = ExecutionCoordinator(PaperExecutionAdapter())
        service = ReconciliationService(coordinator)
        assert await service.start() is True
        assert await service.reconcile_once() is True
        assert service.healthy is True
        await service.stop()

    asyncio.run(scenario())


def test_reconciliation_service_fails_closed_on_remote_failure():
    async def scenario():
        adapter = PaperExecutionAdapter()
        adapter.healthy = False
        coordinator = ExecutionCoordinator(adapter)
        service = ReconciliationService(coordinator)
        assert await service.reconcile_once() is False
        assert service.healthy is False
        assert coordinator.recovery_state == "RECOVERY"

    asyncio.run(scenario())


def test_reconciliation_worker_records_unexpected_failure():
    async def scenario():
        class BrokenAdapter(PaperExecutionAdapter):
            def get_positions(self):
                raise OSError("unexpected reconciliation failure")

        coordinator = ExecutionCoordinator(BrokenAdapter())
        service = ReconciliationService(coordinator)
        await service.start()
        await service._task
        assert service.failed is True
        assert isinstance(service.last_error, OSError)
        assert service.running is False
        await service.stop()

    asyncio.run(scenario())


def test_reconciliation_worker_runs_multiple_bounded_cycles():
    async def scenario():
        coordinator = ExecutionCoordinator(PaperExecutionAdapter())
        service = ReconciliationService(coordinator, interval_seconds=0.01)
        calls = 0
        original = service.reconcile_once

        async def counted_reconcile():
            nonlocal calls
            calls += 1
            return await original()

        service.reconcile_once = counted_reconcile
        await service.start()
        await asyncio.sleep(0.035)
        await service.stop()
        assert calls >= 2
        assert service._task is None

    asyncio.run(scenario())