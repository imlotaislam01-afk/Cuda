from dataclasses import replace

from brain.execution import ExecutionIntent, PaperExecutionEngine


def intent():
    return ExecutionIntent("BTCUSDT", "LONG", 100, 98, 103, 106, None, 1, 5, 2, approved=True)


def test_paper_execution_opens_partially_takes_profit_and_closes():
    engine = PaperExecutionEngine()
    opened = engine.open(intent())
    assert opened.status == "OPEN"
    partial = engine.update(103)
    assert partial.status == "TP1_PARTIAL"
    assert partial.remaining_quantity == 0.5
    closed = engine.update(106)
    assert closed.status == "CLOSED_TARGET"
    assert closed.remaining_quantity == 0


def test_paper_execution_hits_stop_and_rejects_unapproved_intent():
    engine = PaperExecutionEngine()
    try:
        engine.open(replace(intent(), approved=False))
    except ValueError as exc:
        assert "approved" in str(exc)
    else:
        raise AssertionError("Expected unapproved paper intent to be rejected")
    engine.open(intent())
    assert engine.update(98).status == "CLOSED_STOP"


def test_paper_engine_has_no_live_execution_mode():
    assert PaperExecutionEngine.PAPER_ONLY is True
