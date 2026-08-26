import asyncio

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