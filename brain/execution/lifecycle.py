from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from .model import Fill, OrderStatus, PositionSnapshot


@dataclass(frozen=True)
class ExecutionEvent:
    event_type: str
    client_order_id: str | None
    event_time: float
    details: dict[str, Any]

    def to_dict(self):
        return {
            "event_type": self.event_type,
            "client_order_id": self.client_order_id,
            "event_time": self.event_time,
            "details": dict(sorted(self.details.items())),
        }


@dataclass(frozen=True)
class OrderState:
    client_order_id: str
    exchange_order_id: str | None
    symbol: str
    side: str
    status: OrderStatus
    order_type: str
    quantity: float
    filled_quantity: float
    average_fill_price: float | None
    created_at: float
    updated_at: float
    exchange: str
    execution_mode: str
    parent_client_order_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "exchange_order_id": self.exchange_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "status": self.status.value,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "average_fill_price": self.average_fill_price,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "exchange": self.exchange,
            "execution_mode": self.execution_mode,
            "parent_client_order_id": self.parent_client_order_id,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class PositionState:
    symbol: str
    side: str
    quantity: float
    average_price: float | None
    exchange: str
    status: str = "OPEN"
    updated_at: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "exchange": self.exchange,
            "status": self.status,
            "updated_at": self.updated_at,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class ProtectionState:
    client_order_id: str
    exchange_order_id: str | None
    parent_client_order_id: str
    symbol: str
    side: str
    quantity: float
    trigger_price: float | None
    order_type: str
    status: str
    exchange: str
    created_at: float
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "exchange_order_id": self.exchange_order_id,
            "parent_client_order_id": self.parent_client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "trigger_price": self.trigger_price,
            "order_type": self.order_type,
            "status": self.status,
            "exchange": self.exchange,
            "created_at": self.created_at,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class IntentState:
    client_order_id: str
    symbol: str
    status: str
    created_at: float
    payload: dict[str, Any] = field(default_factory=dict)


class ExecutionLedger:
    """Append-only deterministic execution lifecycle record with durable domain state."""

    def __init__(self, db_path: str | None = None, event_listener=None) -> None:
        self.events: list[ExecutionEvent] = []
        self.event_listener = event_listener
        self.fills: dict[str, Fill] = {}
        self.intents: dict[str, IntentState] = {}
        self._kill_switch_state = "RESET"
        self._recovery_state = "READY"
        self._connection = sqlite3.connect(db_path) if db_path else None
        if self._connection is not None:
            self._initialize_schema()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def integrity_check(self) -> bool:
        if self._connection is None:
            return True
        return self._connection.execute("PRAGMA integrity_check").fetchone()[0].lower() == "ok"

    def backup_to(self, destination: str) -> None:
        if self._connection is None:
            raise sqlite3.DatabaseError("Cannot back up an in-memory ledger")
        source = Path(self._connection.execute("PRAGMA database_list").fetchone()[2]).resolve()
        if Path(destination).resolve() == source:
            raise sqlite3.DatabaseError("Backup destination must differ from source")
        self._connection.commit()
        target = sqlite3.connect(destination)
        try:
            self._connection.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0].lower() != "ok":
                raise sqlite3.DatabaseError("Backup integrity check failed")
            target.commit()
        finally:
            target.close()

    def _initialize_schema(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS execution_events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, "
            "client_order_id TEXT, event_time REAL NOT NULL, details_json TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS orders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, client_order_id TEXT UNIQUE NOT NULL, "
            "exchange_order_id TEXT, symbol TEXT NOT NULL, side TEXT NOT NULL, status TEXT NOT NULL, "
            "order_type TEXT NOT NULL, quantity REAL NOT NULL, filled_quantity REAL NOT NULL, "
            "average_fill_price REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL, "
            "exchange TEXT NOT NULL, execution_mode TEXT NOT NULL, parent_client_order_id TEXT, payload_json TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS execution_intents ("
            "client_order_id TEXT PRIMARY KEY NOT NULL, symbol TEXT NOT NULL, status TEXT NOT NULL, "
            "created_at REAL NOT NULL, payload_json TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS positions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT UNIQUE NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL, "
            "average_price REAL, exchange TEXT NOT NULL, status TEXT NOT NULL, updated_at REAL NOT NULL, payload_json TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS fills ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, fill_id TEXT UNIQUE NOT NULL, exchange TEXT NOT NULL, symbol TEXT NOT NULL, "
            "order_id TEXT, client_order_id TEXT NOT NULL, execution_timestamp REAL NOT NULL, side TEXT NOT NULL, "
            "price REAL NOT NULL, quantity REAL NOT NULL, fee REAL, fee_currency TEXT, source TEXT NOT NULL, sequence INTEGER, payload_json TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS protection_orders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, client_order_id TEXT UNIQUE NOT NULL, parent_client_order_id TEXT NOT NULL, "
            "symbol TEXT NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL, trigger_price REAL, order_type TEXT NOT NULL, "
            "status TEXT NOT NULL, exchange TEXT NOT NULL, created_at REAL NOT NULL, payload_json TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS reconciliation ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, payload_json TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS kill_switch_events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, state TEXT NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL, payload_json TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS recovery_events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, state TEXT NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL, payload_json TEXT NOT NULL)"
        )
        columns = {row[1] for row in self._connection.execute("PRAGMA table_info(protection_orders)")}
        if "exchange_order_id" not in columns:
            self._connection.execute("ALTER TABLE protection_orders ADD COLUMN exchange_order_id TEXT")
        self._connection.commit()

    @staticmethod
    def _fill_id(client_order_id: str, quantity: float, price: float, event_time: float, sequence: int | None = None) -> str:
        value = f"{client_order_id}|{quantity:.16g}|{price:.16g}|{event_time:.16g}|{sequence}"
        return "fill-" + hashlib.sha256(value.encode()).hexdigest()[:24]

    def record(self, event_type: str, *, client_order_id: str | None = None, event_time: float = 0.0, **details) -> ExecutionEvent:
        event = ExecutionEvent(event_type, client_order_id, event_time, details)
        self.events.append(event)
        if self._connection is not None:
            self._connection.execute(
                "INSERT INTO execution_events (event_type, client_order_id, event_time, details_json) VALUES (?, ?, ?, ?)",
                (event_type, client_order_id, event_time, json.dumps(details, sort_keys=True, separators=(",", ":"))),
            )
            self._connection.commit()
        if self.event_listener is not None and event_type in {"EXECUTION_FAILURE", "RECOVERY_REQUIRED", "KILL_SWITCH", "ORDER_REJECTED", "UNKNOWN"}:
            safe_details = {key: value for key, value in details.items() if key in {"symbol", "reason", "status", "category"}}
            try:
                self.event_listener(ExecutionEvent(event_type, client_order_id, event_time, safe_details))
            except Exception:
                pass
        return event

    def persist_order(self, order: Any) -> OrderState:
        state = OrderState(
            client_order_id=order.client_order_id,
            exchange_order_id=getattr(order, "exchange_order_id", None),
            symbol=order.symbol,
            side=order.side,
            status=OrderStatus(order.status.value if hasattr(order.status, "value") else str(order.status)),
            order_type=order.order_type,
            quantity=float(order.quantity),
            filled_quantity=float(order.filled_quantity),
            average_fill_price=getattr(order, "average_fill_price", None),
            created_at=float(getattr(order, "created_time", 0.0)),
            updated_at=float(getattr(order, "updated_time", getattr(order, "created_time", 0.0))),
            exchange=getattr(order, "exchange", "PAPER"),
            execution_mode=getattr(order.execution_mode, "value", str(order.execution_mode)),
            parent_client_order_id=getattr(order, "parent_client_order_id", None),
            payload=getattr(order, "metadata", {}) or {},
        )
        if self._connection is None:
            return state

        self._connection.execute(
            "INSERT INTO orders (client_order_id, exchange_order_id, symbol, side, status, order_type, quantity, filled_quantity, average_fill_price, created_at, updated_at, exchange, execution_mode, parent_client_order_id, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(client_order_id) DO UPDATE SET exchange_order_id=excluded.exchange_order_id, symbol=excluded.symbol, side=excluded.side, status=excluded.status, order_type=excluded.order_type, quantity=excluded.quantity, filled_quantity=excluded.filled_quantity, average_fill_price=excluded.average_fill_price, updated_at=excluded.updated_at, exchange=excluded.exchange, execution_mode=excluded.execution_mode, parent_client_order_id=excluded.parent_client_order_id, payload_json=excluded.payload_json",
            (
                state.client_order_id,
                state.exchange_order_id,
                state.symbol,
                state.side,
                state.status.value,
                state.order_type,
                state.quantity,
                state.filled_quantity,
                state.average_fill_price,
                state.created_at,
                state.updated_at,
                state.exchange,
                state.execution_mode,
                state.parent_client_order_id,
                json.dumps(state.payload, sort_keys=True, separators=(",", ":")),
            ),
        )
        self._connection.commit()
        return state

    def persist_intent(self, intent: Any, *, client_order_id: str, status: str = "CREATED", created_at: float = 0.0) -> IntentState:
        state = IntentState(client_order_id, intent.symbol.upper(), status.upper(), float(created_at), intent.to_dict())
        self.intents[client_order_id] = state
        if self._connection is not None:
            self._connection.execute(
                "INSERT INTO execution_intents (client_order_id, symbol, status, created_at, payload_json) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status, payload_json=excluded.payload_json",
                (state.client_order_id, state.symbol, state.status, state.created_at, json.dumps(state.payload, sort_keys=True, separators=(",", ":"))),
            )
            self._connection.commit()
        return state

    def load_intent(self, client_order_id: str) -> IntentState | None:
        if self._connection is None:
            return self.intents.get(client_order_id)
        row = self._connection.execute(
            "SELECT client_order_id, symbol, status, created_at, payload_json FROM execution_intents WHERE client_order_id = ?",
            (client_order_id,),
        ).fetchone()
        if row is None:
            return None
        return IntentState(row[0], row[1], row[2], float(row[3]), json.loads(row[4]) if row[4] else {})

    def load_order(self, client_order_id: str) -> OrderState | None:
        if self._connection is None:
            return None
        row = self._connection.execute(
            "SELECT client_order_id, exchange_order_id, symbol, side, status, order_type, quantity, filled_quantity, average_fill_price, created_at, updated_at, exchange, execution_mode, parent_client_order_id, payload_json FROM orders WHERE client_order_id = ?",
            (client_order_id,),
        ).fetchone()
        if row is None:
            return None
        return OrderState(
            client_order_id=row[0],
            exchange_order_id=row[1],
            symbol=row[2],
            side=row[3],
            status=OrderStatus(row[4]),
            order_type=row[5],
            quantity=float(row[6]),
            filled_quantity=float(row[7]),
            average_fill_price=row[8],
            created_at=float(row[9]),
            updated_at=float(row[10]),
            exchange=row[11],
            execution_mode=row[12],
            parent_client_order_id=row[13],
            payload=json.loads(row[14]) if row[14] else {},
        )

    def record_reconciliation(
        self,
        *args: str,
        symbol: str | None = None,
        status: str | None = None,
        details: dict[str, Any] | None = None,
        event_time: float = 0.0,
    ) -> dict[str, Any]:
        if args:
            positional_symbol = args[0]
            if symbol is None:
                symbol = positional_symbol
            elif positional_symbol != symbol:
                symbol = positional_symbol
        if symbol is None:
            raise TypeError("record_reconciliation() missing required argument: 'symbol'")
        if status is None:
            raise TypeError("record_reconciliation() missing required argument: 'status'")
        payload = details or {}
        self._recovery_state = "READY" if status.upper() in {"MATCH", "OK"} else "RECOVERY"
        if self._connection is not None:
            self._connection.execute(
                "INSERT INTO reconciliation (symbol, status, created_at, payload_json) VALUES (?, ?, ?, ?)",
                (symbol.upper(), status.upper(), float(event_time), json.dumps(payload, sort_keys=True, separators=(",", ":"))),
            )
            self._connection.commit()
        return {"symbol": symbol.upper(), "status": status.upper(), "created_at": float(event_time), "details": payload}

    @property
    def recovery_state(self) -> str:
        if self._connection is None:
            return self._recovery_state
        row = self._connection.execute(
            "SELECT status FROM reconciliation ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return "READY"
        return "RECOVERY" if row[0].upper() not in {"MATCH", "OK"} else self._recovery_state

    def record_recovery_event(self, state: str, reason: str, *, payload: dict[str, Any] | None = None, event_time: float = 0.0) -> None:
        if self._connection is None:
            return
        self._connection.execute(
            "INSERT INTO recovery_events (state, reason, created_at, payload_json) VALUES (?, ?, ?, ?)",
            (state.upper(), reason, float(event_time), json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))),
        )
        self._connection.commit()

    def record_kill_switch(self, state: str, reason: str, *, payload: dict[str, Any] | None = None, event_time: float = 0.0) -> None:
        self._kill_switch_state = state.upper()
        if self._connection is None:
            return
        self._connection.execute(
            "INSERT INTO kill_switch_events (state, reason, created_at, payload_json) VALUES (?, ?, ?, ?)",
            (state.upper(), reason, float(event_time), json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))),
        )
        self._connection.commit()

    @property
    def kill_switch_state(self) -> str:
        if self._connection is None:
            return self._kill_switch_state
        row = self._connection.execute("SELECT state FROM kill_switch_events ORDER BY id DESC LIMIT 1").fetchone()
        return row[0].upper() if row else "RESET"

    def snapshot(self) -> list[dict[str, Any]]:
        if self._connection is None:
            return [event.to_dict() for event in self.events]
        rows = self._connection.execute(
            "SELECT event_type, client_order_id, event_time, details_json FROM execution_events ORDER BY id"
        ).fetchall()
        return [
            ExecutionEvent(event_type, client_order_id, event_time, json.loads(details_json)).to_dict()
            for event_type, client_order_id, event_time, details_json in rows
        ]

    def record_fill(
        self,
        *,
        symbol: str,
        client_order_id: str,
        side: str,
        quantity: float,
        price: float,
        event_time: float,
        fill_id: str | None = None,
        exchange: str = "PAPER",
        order_id: str | None = None,
        fee: float | None = None,
        fee_currency: str | None = None,
        source: str = "EXCHANGE",
        sequence: int | None = None,
        **payload,
    ) -> Fill | None:
        fill = self.create_fill(symbol=symbol, client_order_id=client_order_id, side=side, quantity=quantity, price=price, event_time=event_time, fill_id=fill_id, exchange=exchange, order_id=order_id, fee=fee, fee_currency=fee_currency, source=source, sequence=sequence)
        resolved_id = fill.fill_id
        if resolved_id in self.fills:
            return self.fills[resolved_id]
        if self._connection is None:
            self.fills[resolved_id] = fill
            return fill
        self._connection.execute(
            "INSERT OR IGNORE INTO fills (fill_id, exchange, symbol, order_id, client_order_id, execution_timestamp, side, price, quantity, fee, fee_currency, source, sequence, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fill.fill_id, fill.exchange, fill.symbol, fill.order_id, fill.client_order_id, fill.execution_timestamp, fill.side, fill.price, fill.quantity, fill.fee, fill.fee_currency, fill.source, fill.sequence, json.dumps(payload, sort_keys=True, separators=(",", ":"))),
        )
        self._connection.commit()
        self.fills[resolved_id] = fill
        return fill

    def create_fill(self, *, symbol: str, client_order_id: str, side: str, quantity: float, price: float, event_time: float, fill_id: str | None = None, exchange: str = "PAPER", order_id: str | None = None, fee: float | None = None, fee_currency: str | None = None, source: str = "EXCHANGE", sequence: int | None = None) -> Fill:
        resolved_id = fill_id or self._fill_id(client_order_id, quantity, price, event_time, sequence)
        return Fill(resolved_id, exchange.upper(), symbol.upper(), order_id, client_order_id, float(event_time), side.upper(), float(price), float(quantity), fee, fee_currency, source, sequence)

    def load_fills(self, client_order_id: str) -> tuple[Fill, ...]:
        if self._connection is None:
            return tuple(sorted((fill for fill in self.fills.values() if fill.client_order_id == client_order_id), key=lambda fill: (fill.execution_timestamp, fill.fill_id)))
        rows = self._connection.execute(
            "SELECT fill_id, exchange, symbol, order_id, client_order_id, execution_timestamp, side, price, quantity, fee, fee_currency, source, sequence FROM fills WHERE client_order_id = ? ORDER BY execution_timestamp, fill_id",
            (client_order_id,),
        ).fetchall()
        return tuple(Fill(*row) for row in rows)

    def filled_quantity(self, client_order_id: str) -> float:
        return sum(fill.quantity for fill in self.load_fills(client_order_id))

    def record_confirmed_fill(self, fill: Fill, position: PositionSnapshot, event_type: str, event_details: dict[str, Any], reconciliation_status: str, reconciliation_details: dict[str, Any], event_time: float) -> None:
        if self._connection is None:
            self.fills[fill.fill_id] = fill
            self.persist_position(position)
            self.record(event_type, client_order_id=fill.client_order_id, event_time=event_time, **event_details)
            self.record_reconciliation(position.symbol, status=reconciliation_status, details=reconciliation_details, event_time=event_time)
            return
        try:
            self._connection.execute(
                "INSERT OR IGNORE INTO fills (fill_id, exchange, symbol, order_id, client_order_id, execution_timestamp, side, price, quantity, fee, fee_currency, source, sequence, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (fill.fill_id, fill.exchange, fill.symbol, fill.order_id, fill.client_order_id, fill.execution_timestamp, fill.side, fill.price, fill.quantity, fill.fee, fill.fee_currency, fill.source, fill.sequence, "{}"),
            )
            self._connection.execute(
                "INSERT INTO positions (symbol, side, quantity, average_price, exchange, status, updated_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(symbol) DO UPDATE SET side=excluded.side, quantity=excluded.quantity, average_price=excluded.average_price, exchange=excluded.exchange, status=excluded.status, updated_at=excluded.updated_at, payload_json=excluded.payload_json",
                (position.symbol.upper(), position.side, position.quantity, position.average_price, position.exchange, position.status, event_time, "{}"),
            )
            self._connection.execute(
                "INSERT INTO execution_events (event_type, client_order_id, event_time, details_json) VALUES (?, ?, ?, ?)",
                (event_type, fill.client_order_id, event_time, json.dumps(event_details, sort_keys=True, separators=(",", ":"))),
            )
            self._connection.execute(
                "INSERT INTO reconciliation (symbol, status, created_at, payload_json) VALUES (?, ?, ?, ?)",
                (position.symbol.upper(), reconciliation_status.upper(), event_time, json.dumps(reconciliation_details, sort_keys=True, separators=(",", ":"))),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        self.fills[fill.fill_id] = fill

    def persist_position(self, position: Any) -> PositionState:
        state = PositionState(
            symbol=position.symbol,
            side=position.side,
            quantity=float(position.quantity),
            average_price=getattr(position, "average_price", None),
            exchange=getattr(position, "exchange", "PAPER"),
            status=getattr(position, "status", "OPEN"),
            updated_at=float(getattr(position, "updated_at", 0.0)),
            payload=getattr(position, "payload", {}) or {},
        )
        if self._connection is None:
            return state
        self._connection.execute(
            "INSERT INTO positions (symbol, side, quantity, average_price, exchange, status, updated_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(symbol) DO UPDATE SET side=excluded.side, quantity=excluded.quantity, average_price=excluded.average_price, exchange=excluded.exchange, status=excluded.status, updated_at=excluded.updated_at, payload_json=excluded.payload_json",
            (
                state.symbol,
                state.side,
                state.quantity,
                state.average_price,
                state.exchange,
                state.status,
                state.updated_at,
                json.dumps(state.payload, sort_keys=True, separators=(",", ":")),
            ),
        )
        self._connection.commit()
        return state

    def load_position(self, symbol: str) -> PositionState | None:
        if self._connection is None:
            return None
        row = self._connection.execute(
            "SELECT symbol, side, quantity, average_price, exchange, status, updated_at, payload_json FROM positions WHERE symbol = ?",
            (symbol.upper(),),
        ).fetchone()
        if row is None:
            return None
        return PositionState(
            symbol=row[0],
            side=row[1],
            quantity=float(row[2]),
            average_price=row[3],
            exchange=row[4],
            status=row[5],
            updated_at=float(row[6]),
            payload=json.loads(row[7]) if row[7] else {},
        )

    def record_protection(self, protection: Any) -> ProtectionState:
        state = ProtectionState(
            client_order_id=getattr(protection, "client_order_id", ""),
            exchange_order_id=getattr(protection, "exchange_order_id", None),
            parent_client_order_id=getattr(protection, "parent_client_order_id", ""),
            symbol=protection.symbol,
            side=protection.side,
            quantity=float(protection.quantity),
            trigger_price=getattr(protection, "stop_price", None),
            order_type=protection.order_type,
            status=protection.status.value if hasattr(protection.status, "value") else str(protection.status),
            exchange=getattr(protection, "exchange", "PAPER"),
            created_at=float(getattr(protection, "created_time", 0.0)),
            payload=getattr(protection, "metadata", {}) or {},
        )
        if self._connection is not None:
            self._connection.execute(
                "INSERT INTO protection_orders (client_order_id, exchange_order_id, parent_client_order_id, symbol, side, quantity, trigger_price, order_type, status, exchange, created_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(client_order_id) DO UPDATE SET exchange_order_id=excluded.exchange_order_id, parent_client_order_id=excluded.parent_client_order_id, symbol=excluded.symbol, side=excluded.side, quantity=excluded.quantity, trigger_price=excluded.trigger_price, order_type=excluded.order_type, status=excluded.status, exchange=excluded.exchange, payload_json=excluded.payload_json",
                (
                    state.client_order_id,
                    state.exchange_order_id,
                    state.parent_client_order_id,
                    state.symbol,
                    state.side,
                    state.quantity,
                    state.trigger_price,
                    state.order_type,
                    state.status,
                    state.exchange,
                    state.created_at,
                    json.dumps(state.payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            self._connection.commit()
        return state

    def load_protections(self, parent_client_order_id: str) -> tuple[ProtectionState, ...]:
        if self._connection is None:
            return ()
        rows = self._connection.execute(
            "SELECT client_order_id, exchange_order_id, parent_client_order_id, symbol, side, quantity, trigger_price, order_type, status, exchange, created_at, payload_json FROM protection_orders WHERE parent_client_order_id = ? ORDER BY client_order_id",
            (parent_client_order_id,),
        ).fetchall()
        return tuple(ProtectionState(row[0], row[1], row[2], row[3], row[4], float(row[5]), row[6], row[7], row[8], row[9], float(row[10]), json.loads(row[11]) if row[11] else {}) for row in rows)
