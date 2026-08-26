from __future__ import annotations

from dataclasses import replace

from .adapter import InMemoryExecutionAdapter
from .model import ExecutionMode, OrderStatus, PositionSnapshot


class PaperExecutionAdapter(InMemoryExecutionAdapter):
    """Paper adapter implementing the exchange contract without network access."""

    def submit_order(self, order):
        if order.execution_mode is not ExecutionMode.PAPER:
            raise ValueError("Paper adapter accepts PAPER orders only")
        existing = self.orders.get(order.client_order_id)
        if existing is not None:
            return existing
        if order.reduce_only:
            self.orders[order.client_order_id] = order
            return order
        accepted = replace(order, status=OrderStatus.FILLED, filled_quantity=order.quantity, average_fill_price=order.price)
        self.orders[order.client_order_id] = accepted
        self.positions = [PositionSnapshot(order.symbol, "LONG" if order.side == "BUY" else "SHORT", order.quantity, order.price, self.exchange)]
        return accepted
