import sqlite3

import pytest

from brain.execution import ExecutionCoordinator, ExecutionLedger, PaperExecutionAdapter
from brain.runtime import EngineSupervisor, LifecycleState
from config.runtime import RuntimeConfig


class MalformedAccountAdapter(PaperExecutionAdapter):
    def get_account_state(self):
        return {"available_balance": "not-a-number"}


def test_malformed_account_state_blocks_runtime_startup():
    coordinator = ExecutionCoordinator(MalformedAccountAdapter())
    supervisor = EngineSupervisor(config=RuntimeConfig(), coordinator=coordinator)

    assert supervisor.start() is False
    assert supervisor.state is LifecycleState.DEGRADED
    assert supervisor.execution_allowed is False


def test_corrupt_ledger_cannot_become_a_running_supervisor(tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE broken (value TEXT)")
    connection.commit()
    connection.close()
    path.write_bytes(b"not sqlite")

    with pytest.raises(sqlite3.DatabaseError):
        ExecutionLedger(str(path))