from brain.execution import ExecutionConfig, ExecutionCoordinator, ExecutionLedger, PaperExecutionAdapter
from tests.execution.test_p3_foundation import intent


def test_approved_intent_is_persisted_before_submission(tmp_path):
    path = str(tmp_path / "intents.sqlite3")
    config = ExecutionConfig(state_db_path=path)
    outcome = ExecutionCoordinator(PaperExecutionAdapter(), config).submit_intent(intent(), now=7)
    restored = ExecutionLedger(path)
    durable = restored.load_intent(outcome.order.client_order_id)
    assert durable is not None
    assert durable.status == "APPROVED"
    assert durable.payload["symbol"] == "BTCUSDT"