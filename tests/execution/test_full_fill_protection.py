from brain.execution import ExecutionConfig, ExecutionCoordinator, PaperExecutionAdapter, OrderStatus
from tests.execution.test_p3_foundation import intent


def test_full_fill_requires_verified_protection():
    adapter = PaperExecutionAdapter()
    coordinator = ExecutionCoordinator(adapter, ExecutionConfig())
    outcome = coordinator.submit_intent(intent(), now=1)

    assert outcome.status == "SUBMITTED"
    protection = [
        order for order in adapter.orders.values()
        if order.parent_client_order_id == outcome.order.client_order_id
    ]
    assert len(protection) >= 2
    assert all(order.status in {OrderStatus.NEW, OrderStatus.ACKNOWLEDGED} for order in protection)
    assert all(order.quantity == outcome.order.filled_quantity for order in protection)