from brain.main import main


def test_main_orchestration_runs(capsys):
    main()
    output = capsys.readouterr().out
    assert "APEX BRAIN" in output
    assert "EXECUTE:" in output