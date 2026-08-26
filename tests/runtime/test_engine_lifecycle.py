from __future__ import annotations

from brain.execution import ExecutionConfig, ExecutionMode, PaperExecutionAdapter
from brain.runtime import EngineSupervisor, LifecycleState
from config.runtime import RuntimeConfig


def test_engine_supervisor_starts_in_paper_mode_and_reports_runtime_state():
    config = RuntimeConfig(mode=ExecutionMode.PAPER)
    supervisor = EngineSupervisor(config=config)

    assert supervisor.state == LifecycleState.STARTING
    assert supervisor.start() is True
    assert supervisor.state in {LifecycleState.READY, LifecycleState.RUNNING}
    assert supervisor.health.execution_ready is True

    stopped = supervisor.stop()
    assert stopped is True
    assert supervisor.state in {LifecycleState.STOPPING, LifecycleState.STOPPED}


def test_engine_supervisor_is_idempotent_and_safe_before_start():
    supervisor = EngineSupervisor(config=RuntimeConfig())

    assert supervisor.stop() is True
    assert supervisor.start() is True
    assert supervisor.start() is False
    assert supervisor.stop() is True
    assert supervisor.stop() is True


def test_runtime_recovery_blocks_execution_until_reconciliation_is_conclusive():
    config = RuntimeConfig(mode=ExecutionMode.PAPER)
    supervisor = EngineSupervisor(config=config)
    supervisor.ledger.record_reconciliation("BTCUSDT", status="UNKNOWN", details={"reason": "test"}, event_time=1.0)

    assert supervisor.state == LifecycleState.STARTING
    assert supervisor.recovery_manager.is_recovery_required() is True
    assert supervisor.health.execution_ready is False
