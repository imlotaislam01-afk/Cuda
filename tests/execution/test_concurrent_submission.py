from concurrent.futures import ThreadPoolExecutor

from brain.execution import ExecutionConfig, ExecutionCoordinator, PaperExecutionAdapter
from tests.execution.test_p3_foundation import intent


def test_concurrent_identical_intents_have_one_submission():
    coordinator = ExecutionCoordinator(PaperExecutionAdapter(), ExecutionConfig())
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: coordinator.submit_intent(intent(), now=1), range(8)))

    assert sum(outcome.status == "SUBMITTED" for outcome in outcomes) == 1
    assert sum(outcome.status == "DUPLICATE" for outcome in outcomes) == 7