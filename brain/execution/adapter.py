from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .model import OrderRequest, OrderStatus, PositionSnapshot, ReconciliationResult
from .reconciliation import reconcile_positions


class ExchangeExecutionAdapter(ABC):
    """Exchange-neutral private execution contract."""

    exchange: str

    @abstractmethod
    def get_account_state(self) -> dict[str, Any]: ...

    @abstractmethod
    def get_balances(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_positions(self) -> list[PositionSnapshot]: ...

    @abstractmethod
    def get_open_orders(self) -> list[OrderRequest]: ...

    @abstractmethod
    def get_instrument_metadata(self, symbol: str) -> dict[str, Any]: ...

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> OrderRequest: ...

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> OrderRequest: ...

    @abstractmethod
    def amend_order(self, order: OrderRequest) -> OrderRequest: ...

    @abstractmethod
    def get_order(self, client_order_id: str) -> OrderRequest | None: ...

    @abstractmethod
    def reconcile(self, expected: PositionSnapshot | None = None) -> ReconciliationResult: ...

    @abstractmethod
    def health_check(self) -> bool: ...


class InMemoryExecutionAdapter(ExchangeExecutionAdapter):
    """Deterministic adapter used by PAPER, SHADOW, and safe tests."""

    def __init__(self, exchange: str = "PAPER", available_balance: float = float("inf")) -> None:
        self.exchange = exchange.upper()
        self.available_balance = available_balance
        self.orders: dict[str, OrderRequest] = {}
        self.positions: list[PositionSnapshot] = []
        self.healthy = True

    def get_account_state(self):
        return {"healthy": self.healthy, "available_balance": self.available_balance}

    def get_balances(self):
        return [{"asset": "USDT", "available": self.available_balance}]

    def get_positions(self):
        return list(self.positions)

    def get_open_orders(self):
        return [order for order in self.orders.values() if order.status.value in {"NEW", "PARTIALLY_FILLED"}]

    def get_instrument_metadata(self, symbol):
        return {"symbol": symbol.upper(), "quantity_step": 0.001, "price_tick": 0.01, "min_quantity": 0.001}

    def submit_order(self, order):
        existing = self.orders.get(order.client_order_id)
        if existing is not None:
            return existing
        if not self.healthy:
            raise ConnectionError("exchange unavailable")
        self.orders[order.client_order_id] = order
        return order

    def cancel_order(self, client_order_id):
        existing = self.orders.get(client_order_id)
        if existing is None:
            raise KeyError(client_order_id)
        from dataclasses import replace
        canceled = replace(existing, status=OrderStatus.CANCELED)
        self.orders[client_order_id] = canceled
        return canceled

    def amend_order(self, order):
        if order.client_order_id not in self.orders:
            raise KeyError(order.client_order_id)
        self.orders[order.client_order_id] = order
        return order

    def get_order(self, client_order_id):
        return self.orders.get(client_order_id)

    def reconcile(self, expected=None):
        return reconcile_positions(expected, list(self.positions))

    def health_check(self):
        return self.healthy
