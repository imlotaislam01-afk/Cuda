from brain.main import build_runtime, main
from brain.runtime import EngineSupervisor, LifecycleState
from config.runtime import RuntimeConfig


def test_main_orchestration_runs(capsys, monkeypatch):
    async def fake_run_forever(self, context_provider=None):
        self.state = LifecycleState.STOPPED
        return True

    monkeypatch.setattr(EngineSupervisor, "run_forever", fake_run_forever)
    main()
    output = capsys.readouterr().out
    assert "APEX BRAIN" in output
    assert "EXECUTE:" in output


def test_build_runtime_composes_signal_owned_supervisor():
    supervisor, context_provider = build_runtime(RuntimeConfig())

    assert supervisor.shutdown_manager is not None
    assert supervisor.market_data is not None
    assert supervisor.brain_loop is not None
    assert supervisor.execution_consumer is not None
    assert supervisor.reconciliation_service is not None
    assert context_provider() is None