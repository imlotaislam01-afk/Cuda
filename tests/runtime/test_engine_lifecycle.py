from __future__ import annotations

import asyncio
from types import SimpleNamespace

from brain.execution import ExecutionConfig, ExecutionCoordinator, ExecutionMode, ExecutionLedger, PaperExecutionAdapter
from brain.runtime import BrainLoop, ExecutionConsumer, EngineSupervisor, LifecycleState
from config.runtime import RuntimeConfig
from tests.execution.test_p3_foundation import intent


class RuntimeComponent:
    def __init__(self, name, events, ready=True):
        self.name = name
        self.events = events
        self.ready = ready
        self.running = False

    async def start(self):
        self.events.append(f"start:{self.name}")
        self.running = True
        return True

    async def stop(self):
        self.events.append(f"stop:{self.name}")
        self.running = False
        return True


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


def test_engine_supervisor_emits_durable_lifecycle_observability():
    config = RuntimeConfig(mode=ExecutionMode.PAPER)
    supervisor = EngineSupervisor(config=config)
    assert supervisor.start() is True
    snapshot = supervisor.ledger.snapshot()
    event_names = {event["event_type"] for event in snapshot}
    assert "RUNTIME_START" in event_names
    assert "RUNTIME_RECOVERY" in event_names
    assert "RUNTIME_READY" in event_names
    assert "RUNTIME_RUNNING" in event_names
    supervisor.stop()
    assert any(event["event_type"] == "RUNTIME_STOPPING" for event in supervisor.ledger.snapshot())
    assert any(event["event_type"] == "RUNTIME_STOPPED" for event in supervisor.ledger.snapshot())


def test_engine_supervisor_owns_ordered_runtime_components():
    async def scenario():
        events = []
        components = [RuntimeComponent(name, events) for name in ("market", "brain", "execution", "reconciliation", "dashboard")]
        supervisor = EngineSupervisor(
            config=RuntimeConfig(),
            market_data=components[0],
            brain_loop=components[1],
            execution_consumer=components[2],
            reconciliation_service=components[3],
            dashboard=components[4],
        )

        assert await supervisor.start_runtime() is True
        assert supervisor.state is LifecycleState.RUNNING
        assert events == ["start:market", "start:brain", "start:execution", "start:reconciliation", "start:dashboard"]
        assert await supervisor.stop_runtime() is True
        assert supervisor.state is LifecycleState.STOPPED
        assert events[-5:] == ["stop:dashboard", "stop:reconciliation", "stop:execution", "stop:brain", "stop:market"]

    asyncio.run(scenario())


def test_engine_supervisor_runs_brain_to_execution_consumer_until_shutdown(tmp_path):
    async def scenario():
        events = []
        context = SimpleNamespace(symbol="BTCUSDT", event_time=1.0)
        pipeline = SimpleNamespace(run=lambda value: SimpleNamespace(context=value, intent=intent()))
        brain = BrainLoop(pipeline, clock=lambda: 1.0)
        ledger = ExecutionLedger(str(tmp_path / "runtime.sqlite3"))
        coordinator = ExecutionCoordinator(PaperExecutionAdapter(), ExecutionConfig(), ledger)
        execution = ExecutionConsumer(coordinator)
        components = [RuntimeComponent(name, events) for name in ("market", "reconciliation", "dashboard")]
        supervisor = EngineSupervisor(
            config=RuntimeConfig(),
            ledger=ledger,
            coordinator=coordinator,
            market_data=components[0],
            brain_loop=brain,
            execution_consumer=execution,
            reconciliation_service=components[1],
            dashboard=components[2],
        )
        calls = 0

        def provide_context():
            nonlocal calls
            calls += 1
            if calls >= 3:
                supervisor.state = LifecycleState.STOPPING
                return None
            return context

        assert await supervisor.run_forever(provide_context, poll_interval=0.01) is True
        assert calls >= 3
        assert len(execution.outcomes) == 1
        assert execution.outcomes[0].status == "SUBMITTED"
        assert supervisor.state is LifecycleState.STOPPED
        assert events == ["start:market", "start:reconciliation", "start:dashboard", "stop:dashboard", "stop:reconciliation", "stop:market"]

    asyncio.run(scenario())
