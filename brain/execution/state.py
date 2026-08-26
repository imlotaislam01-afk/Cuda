from __future__ import annotations

from dataclasses import dataclass

from .model import OrderRequest, OrderStatus


@dataclass
class OrderStateMachine:
    order: OrderRequest

    def transition(self, status: OrderStatus) -> OrderRequest:
        current = self.order.status
        allowed = {
            OrderStatus.NEW: {OrderStatus.SUBMITTING, OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCEL_PENDING, OrderStatus.CANCELED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED},
            OrderStatus.SUBMITTING: {OrderStatus.ACKNOWLEDGED, OrderStatus.UNKNOWN, OrderStatus.REJECTED},
            OrderStatus.ACKNOWLEDGED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCEL_PENDING, OrderStatus.CANCELED, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
            OrderStatus.PARTIALLY_FILLED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCEL_PENDING, OrderStatus.CANCELED, OrderStatus.CANCELLED},
            OrderStatus.FILLED: {OrderStatus.FILLED},
            OrderStatus.CANCEL_PENDING: {OrderStatus.CANCELED, OrderStatus.CANCELLED, OrderStatus.UNKNOWN},
            OrderStatus.CANCELED: {OrderStatus.CANCELED},
            OrderStatus.CANCELLED: {OrderStatus.CANCELLED},
            OrderStatus.REJECTED: {OrderStatus.REJECTED},
            OrderStatus.UNKNOWN: set(OrderStatus),
        }.get(current, set())
        if status not in allowed:
            raise ValueError(f"Invalid order transition: {current.value} -> {status.value}")
        from dataclasses import replace
        self.order = replace(self.order, status=status)
        return self.order
