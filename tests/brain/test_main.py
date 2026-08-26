from brain.main import main
from brain.runtime import EngineSupervisor, LifecycleState


def test_main_orchestration_runs(capsys, monkeypatch):
    async def fake_run_forever(self, context_provider):
        self.state = LifecycleState.STOPPED
        return True

    monkeypatch.setattr(EngineSupervisor, "run_forever", fake_run_forever)
    main()
    output = capsys.readouterr().out
    assert "APEX BRAIN" in output
    assert "EXECUTE:" in output