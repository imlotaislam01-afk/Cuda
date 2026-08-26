from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .intent import ExecutionIntent


@dataclass(frozen=True)
class PaperPosition:
    symbol: str
    side: str
    entry: float
    quantity: float
    stop_loss: float
    tp1: float | None
    tp2: float | None
    remaining_quantity: float
    realized_pnl: float
    unrealized_pnl: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class PaperExecutionEngine:
    """Deterministic paper-only execution simulator."""

    PAPER_ONLY = True

    def __init__(self, fee_rate: float = 0.0, slippage_rate: float = 0.0):
        if fee_rate < 0 or slippage_rate < 0:
            raise ValueError("Fees and slippage cannot be negative")
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.position: PaperPosition | None = None
        self.realized_pnl = 0.0

    def open(self, intent: ExecutionIntent, *, price: float | None = None) -> PaperPosition:
        if not self.PAPER_ONLY or not intent.paper_only:
            raise ValueError("Paper-only intent required")
        if not intent.approved:
            raise ValueError("Risk-approved intent required")
        if self.position is not None and self.position.status == "OPEN":
            raise ValueError("Paper position already open")
        entry = float(price if price is not None else intent.entry)
        if entry <= 0 or intent.quantity <= 0 or intent.stop_loss <= 0:
            raise ValueError("Paper execution requires positive entry, stop, and quantity")
        if intent.action == "LONG" and intent.stop_loss >= entry:
            raise ValueError("Long stop-loss must be below entry")
        if intent.action == "SHORT" and intent.stop_loss <= entry:
            raise ValueError("Short stop-loss must be above entry")
        for target in (intent.tp1, intent.tp2, intent.tp3):
            if target is not None and (target <= entry if intent.action == "LONG" else target >= entry):
                raise ValueError("Take-profit must be on the profitable side of entry")
        entry *= 1 + self.slippage_rate if intent.action == "LONG" else 1 - self.slippage_rate
        fee = entry * intent.quantity * self.fee_rate
        self.position = PaperPosition(intent.symbol, intent.action, entry, intent.quantity, intent.stop_loss, intent.tp1, intent.tp2, intent.quantity, -fee, 0.0, "OPEN")
        self.realized_pnl = -fee
        return self.position

    def update(self, price: float) -> PaperPosition:
        if self.position is None:
            raise ValueError("No paper position is open")
        position = self.position
        move = (price - position.entry) if position.side == "LONG" else (position.entry - price)
        unrealized = move * position.remaining_quantity
        hit_stop = price <= position.stop_loss if position.side == "LONG" else price >= position.stop_loss
        hit_tp2 = position.tp2 is not None and (price >= position.tp2 if position.side == "LONG" else price <= position.tp2)
        hit_tp1 = position.tp1 is not None and (price >= position.tp1 if position.side == "LONG" else price <= position.tp1)
        status = "OPEN"
        remaining = position.remaining_quantity
        realized = position.realized_pnl
        if hit_stop:
            realized += (position.stop_loss - position.entry) * remaining if position.side == "LONG" else (position.entry - position.stop_loss) * remaining
            remaining = 0.0
            status = "CLOSED_STOP"
        elif hit_tp2:
            realized += unrealized
            remaining = 0.0
            status = "CLOSED_TARGET"
        elif hit_tp1 and position.tp1 is not None:
            partial = position.remaining_quantity / 2
            realized += (position.tp1 - position.entry) * partial if position.side == "LONG" else (position.entry - position.tp1) * partial
            remaining -= partial
            status = "TP1_PARTIAL"
        self.realized_pnl = realized
        self.position = PaperPosition(position.symbol, position.side, position.entry, position.quantity, position.stop_loss, position.tp1, position.tp2, remaining, realized, unrealized if remaining else 0.0, status)
        return self.position

    def trail(self, stop_loss: float) -> PaperPosition:
        if self.position is None or self.position.status != "OPEN":
            raise ValueError("No open paper position is available for trailing")
        position = self.position
        if position.side == "LONG" and stop_loss <= position.stop_loss:
            raise ValueError("Long trailing stop must move upward")
        if position.side == "SHORT" and stop_loss >= position.stop_loss:
            raise ValueError("Short trailing stop must move downward")
        self.position = PaperPosition(
            position.symbol, position.side, position.entry, position.quantity,
            float(stop_loss), position.tp1, position.tp2, position.remaining_quantity,
            position.realized_pnl, position.unrealized_pnl, position.status,
        )
        return self.position

    def close(self, price: float) -> PaperPosition:
        if self.position is None:
            raise ValueError("No paper position is open")
        position = self.position
        pnl = ((price - position.entry) if position.side == "LONG" else (position.entry - price)) * position.remaining_quantity
        self.realized_pnl = position.realized_pnl + pnl
        self.position = PaperPosition(position.symbol, position.side, position.entry, position.quantity, position.stop_loss, position.tp1, position.tp2, 0.0, self.realized_pnl, 0.0, "CLOSED")
        return self.position
