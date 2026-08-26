from brain.execution import ExecutionConfig, ExecutionCoordinator, ExecutionLedger, PaperExecutionAdapter
from tests.execution.test_p3_foundation import intent


def test_restart_does_not_resubmit_durable_order_when_remote_state_is_missing(tmp_path):
    path = str(tmp_path / "restart-idempotency.sqlite3")
    config = ExecutionConfig(state_db_path=path)
    first = ExecutionCoordinator(PaperExecutionAdapter(), config)
    outcome = first.submit_intent(intent(), now=1)

    restarted = ExecutionCoordinator(PaperExecutionAdapter(), config)
    retry = restarted.submit_intent(intent(), now=2)

    assert outcome.status == "SUBMITTED"
    assert retry.reason == "RECOVERY_REQUIRED"
    assert restarted.recovery_state == "RECOVERY"
    assert ExecutionLedger(path).load_order(outcome.order.client_order_id) is not None