from __future__ import annotations

from dataclasses import dataclass

from .model import ExecutionMode, OrderRequest, OrderStatus


@dataclass(frozen=True)
class ProtectionResult:
    verified: bool
    stop_loss: float | None
    take_profit: float | None
    reason: str | None = None

    def to_dict(self):
        return dict(vars(self))


class ProtectionManager:
    """Validate and verify protective orders without assuming exchange success."""

    def create_plan(self, intent, *, exchange: str = "PAPER", mode: ExecutionMode = ExecutionMode.PAPER, quantity: float | None = None) -> tuple[OrderRequest, ...]:
        if not intent.approved:
            raise ValueError("Protection requires an approved intent")
        if intent.action == "LONG" and not intent.stop_loss < intent.entry:
            raise ValueError("Long stop-loss must be below entry")
        if intent.action == "SHORT" and not intent.stop_loss > intent.entry:
            raise ValueError("Short stop-loss must be above entry")
        effective_quantity = float(intent.quantity if quantity is None else quantity)
        if effective_quantity <= 0 or effective_quantity > float(intent.quantity):
            raise ValueError("Protection quantity must be positive and no greater than requested quantity")
        entry = OrderRequest.from_intent(intent, exchange=exchange, mode=mode)
        orders = [entry]
        orders.append(OrderRequest(
            client_order_id=f"{entry.client_order_id}-sl", exchange_order_id=None,
            symbol=intent.symbol, side="SELL" if intent.action == "LONG" else "BUY",
            order_type="STOP_MARKET", quantity=effective_quantity, stop_price=float(intent.stop_loss),
            reduce_only=True, close_position=False, leverage=float(intent.leverage),
            exchange=exchange, execution_mode=mode, parent_client_order_id=entry.client_order_id,
        ))
        for index, target in enumerate((intent.tp1, intent.tp2, intent.tp3), start=1):
            if target is None:
                continue
            orders.append(OrderRequest(
                client_order_id=f"{entry.client_order_id}-tp{index}", exchange_order_id=None,
                symbol=intent.symbol, side="SELL" if intent.action == "LONG" else "BUY",
                order_type="TAKE_PROFIT", quantity=effective_quantity, price=float(target), stop_price=float(target),
                reduce_only=True, close_position=False, leverage=float(intent.leverage),
                exchange=exchange, execution_mode=mode,
                parent_client_order_id=entry.client_order_id,
            ))
        return tuple(orders)

    def verify(self, entry: OrderRequest, protection_orders) -> ProtectionResult:
        protections = [order for order in protection_orders if order.parent_client_order_id == entry.client_order_id and order.reduce_only and order.status in {OrderStatus.NEW, OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED}]
        stops = [order for order in protections if order.stop_price is not None]
        targets = [order for order in protections if order.order_type == "TAKE_PROFIT"]
        if not stops or not targets:
            return ProtectionResult(False, None, None, "PROTECTION_MISSING")
        if any(order.quantity < entry.filled_quantity for order in protections):
            return ProtectionResult(False, stops[0].stop_price, targets[0].price, "PROTECTION_INSUFFICIENT")
        return ProtectionResult(True, stops[0].stop_price, targets[0].price)
