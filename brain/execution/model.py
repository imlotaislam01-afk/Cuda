from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecutionMode(str, Enum):
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class OrderStatus(str, Enum):
    NEW = "NEW"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELED = "CANCELED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class DiscrepancyCategory(str, Enum):
    MISSING_POSITION = "MISSING_POSITION"
    UNEXPECTED_POSITION = "UNEXPECTED_POSITION"
    POSITION_SIDE_MISMATCH = "SIDE_MISMATCH"
    POSITION_QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    AVERAGE_PRICE_MISMATCH = "AVERAGE_PRICE_MISMATCH"
    ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"
    FILL_QUANTITY_MISMATCH = "FILL_QUANTITY_MISMATCH"
    PROTECTION_MISSING = "PROTECTION_MISSING"
    PROTECTION_INSUFFICIENT = "PROTECTION_INSUFFICIENT"
    REMOTE_STATE_UNAVAILABLE = "REMOTE_STATE_UNAVAILABLE"


class RecoveryState(str, Enum):
    READY = "READY"
    RECOVERY = "RECOVERY"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Fill:
    fill_id: str
    exchange: str
    symbol: str
    order_id: str | None
    client_order_id: str
    execution_timestamp: float
    side: str
    price: float
    quantity: float
    fee: float | None = None
    fee_currency: str | None = None
    source: str = "EXCHANGE"
    sequence: int | None = None

    def __post_init__(self):
        if not self.fill_id or not self.client_order_id or not self.symbol:
            raise ValueError("Fill identity is required")
        if self.quantity <= 0 or self.price <= 0:
            raise ValueError("Fill quantity and price must be positive")
        if self.side.upper() not in {"BUY", "SELL"}:
            raise ValueError("Fill side must be BUY or SELL")

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class ExecutionConfig:
    mode: ExecutionMode = ExecutionMode.PAPER
    live_enabled: bool = False
    global_kill_switch: bool = False
    exchange_kill_switch: bool = False
    symbol_kill_switches: frozenset[str] = frozenset()
    max_order_notional: float = 0.0
    max_position_notional: float = 0.0
    max_leverage: float = 5.0
    stale_intent_after: float = 30.0
    credentials: dict[str, str] = field(default_factory=dict)
    exchange: str = "PAPER"
    base_url: str | None = None
    recv_window: int = 5000
    timeout: float = 10.0
    symbol: str | None = None
    state_db_path: str | None = None

    def allows_submission(self, exchange: str, symbol: str) -> bool:
        if self.mode is ExecutionMode.LIVE:
            return self.live_enabled and bool(self.credentials.get("api_key")) and bool(self.credentials.get("api_secret"))
        return self.mode in {ExecutionMode.PAPER, ExecutionMode.TESTNET, ExecutionMode.SHADOW}


@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str
    exchange_order_id: str | None
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    reduce_only: bool = False
    close_position: bool = False
    leverage: float = 1.0
    margin_mode: str = "ISOLATED"
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    created_time: float = 0.0
    updated_time: float = 0.0
    exchange: str = ""
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    parent_client_order_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.side.upper() not in {"BUY", "SELL"}:
            raise ValueError("Order side must be BUY or SELL")
        if self.quantity < 0 or (self.quantity == 0 and not self.close_position):
            raise ValueError("Order quantity must be positive unless close_position is set")
        if self.close_position and self.quantity != 0:
            raise ValueError("close_position cannot include quantity")
        if self.close_position and self.reduce_only:
            raise ValueError("close_position cannot be combined with reduce_only")
        if self.order_type in {"STOP_MARKET", "TAKE_PROFIT"} and (self.stop_price is None or self.stop_price <= 0):
            raise ValueError(f"{self.order_type} requires a positive trigger price")

    def to_dict(self) -> dict[str, Any]:
        result = dict(vars(self))
        result["status"] = self.status.value
        result["execution_mode"] = self.execution_mode.value
        result["metadata"] = dict(sorted(self.metadata.items()))
        return result

    @classmethod
    def from_intent(cls, intent, *, exchange: str = "PAPER", mode: ExecutionMode = ExecutionMode.PAPER, created_time: float = 0.0) -> "OrderRequest":
        client_order_id = deterministic_client_order_id(intent, exchange=exchange, mode=mode)
        return cls(
            client_order_id=client_order_id,
            exchange_order_id=None,
            symbol=intent.symbol,
            side="BUY" if intent.action == "LONG" else "SELL",
            order_type="MARKET",
            quantity=float(intent.quantity),
            price=float(intent.entry),
            stop_price=None,
            leverage=float(intent.leverage),
            exchange=exchange.upper(),
            execution_mode=mode,
            created_time=created_time,
            updated_time=created_time,
            metadata={"intent_action": intent.action, "tp1": intent.tp1, "tp2": intent.tp2, "tp3": intent.tp3},
        )


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    side: str
    quantity: float
    average_price: float | None
    exchange: str
    status: str = "OPEN"

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    discrepancies: tuple[DiscrepancyCategory | str, ...] = ()
    expected: PositionSnapshot | None = None
    actual: PositionSnapshot | None = None
    stale_orders: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "discrepancies": [item.value if isinstance(item, Enum) else item for item in self.discrepancies],
            "expected": self.expected.to_dict() if self.expected else None,
            "actual": self.actual.to_dict() if self.actual else None,
            "stale_orders": list(self.stale_orders),
        }


def deterministic_client_order_id(intent, *, exchange: str = "PAPER", mode: ExecutionMode = ExecutionMode.PAPER) -> str:
    payload = {
        "exchange": exchange.upper(),
        "mode": mode.value,
        "symbol": intent.symbol.upper(),
        "action": intent.action,
        "entry": intent.entry,
        "stop_loss": intent.stop_loss,
        "tp1": intent.tp1,
        "tp2": intent.tp2,
        "tp3": intent.tp3,
        "quantity": intent.quantity,
        "leverage": intent.leverage,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
    return f"apex-{digest}"
