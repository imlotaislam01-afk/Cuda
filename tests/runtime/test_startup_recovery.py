from brain.runtime import EngineSupervisor, LifecycleState
from config.runtime import RuntimeConfig


def test_paper_startup_recovery_checks_remote_account_and_state():
    supervisor = EngineSupervisor(config=RuntimeConfig())
    assert supervisor.start() is True
    assert supervisor.state is LifecycleState.RUNNING
    assert supervisor.health.exchange_ok is True
    assert supervisor.health.account_ok is True
    supervisor.stop()


def test_startup_recovery_fails_closed_when_exchange_is_unavailable():
    supervisor = EngineSupervisor(config=RuntimeConfig())
    supervisor.coordinator.adapter.healthy = False
    assert supervisor.start() is False
    assert supervisor.state is LifecycleState.DEGRADED
    assert supervisor.execution_allowed is False