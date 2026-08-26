import sqlite3

import pytest

from brain.execution import ExecutionCoordinator, ExecutionLedger, PaperExecutionAdapter, PositionSnapshot
from brain.runtime import EngineSupervisor, LifecycleState
from config.runtime import RuntimeConfig


class MalformedAccountAdapter(PaperExecutionAdapter):
    def get_account_state(self):
        return {"available_balance": "not-a-number"}


class BrokenRecoveryAdapter(PaperExecutionAdapter):
    def get_open_orders(self):
        raise OSError("remote order state failed")


class UnprotectedPositionAdapter(PaperExecutionAdapter):
    def __init__(self):
        super().__init__()
        self.positions = [PositionSnapshot("BTCUSDT", "LONG", 1.0, 100.0, "PAPER")]


def test_malformed_account_state_blocks_runtime_startup():
    coordinator = ExecutionCoordinator(MalformedAccountAdapter())
    supervisor = EngineSupervisor(config=RuntimeConfig(), coordinator=coordinator)

    assert supervisor.start() is False
    assert supervisor.state is LifecycleState.DEGRADED
    assert supervisor.execution_allowed is False


def test_unexpected_recovery_failure_degrades_runtime_fail_closed():
    coordinator = ExecutionCoordinator(BrokenRecoveryAdapter())
    supervisor = EngineSupervisor(config=RuntimeConfig(), coordinator=coordinator)

    assert supervisor.start() is False
    assert supervisor.state is LifecycleState.DEGRADED
    assert supervisor.health.execution_ready is False
    assert supervisor.recovery_manager.last_error == "remote order state failed"


def test_startup_recovery_blocks_active_position_without_protection():
    coordinator = ExecutionCoordinator(UnprotectedPositionAdapter())
    supervisor = EngineSupervisor(config=RuntimeConfig(), coordinator=coordinator)

    assert supervisor.start() is False
    assert supervisor.state is LifecycleState.DEGRADED
    assert supervisor.execution_allowed is False
    assert "protection" in supervisor.recovery_manager.last_error.lower()


def test_corrupt_ledger_cannot_become_a_running_supervisor(tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE broken (value TEXT)")
    connection.commit()
    connection.close()
    path.write_bytes(b"not sqlite")

    with pytest.raises(sqlite3.DatabaseError):
        ExecutionLedger(str(path))