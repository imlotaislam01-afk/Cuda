import asyncio
import json
import time
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from market.integration.oi_history import OIHistory
from market.integration.funding_history import FundingHistory
from market.integration.price_history import PriceHistory

try:
    import websockets
except ImportError:  # pragma: no cover - exercised in dependency-free installs
    websockets = None


BYBIT_PUBLIC_WS = "wss://stream.bybit.com/v5/public/linear"


def normalize_bybit_interval(interval: str | int) -> str:
    """Return the canonical timeframe name used by the intelligence engines."""
    value = str(interval).upper()
    if value == "D":
        return "1d"
    minutes = int(value)
    return f"{minutes // 60}h" if minutes >= 60 and minutes % 60 == 0 else f"{minutes}m"


@dataclass
class BybitMarketData:

    symbol: str

    price: float | None = None

    # Local reconstructed order book.
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)

    trades: list[dict[str, Any]] = field(
        default_factory=list
    )

    last_trade_id: str | None = None
    trade_ids: set[str] = field(default_factory=set)
    last_trade_event_time: float | None = None
    last_update: float = 0.0
    last_event_time: float | None = None
    orderbook_event_time: float | None = None
    last_sequence: int | None = None
    book_ready: bool = False
    book_invalid: bool = False
    data_quality: str = "DATA_INCOMPLETE"
    quality_reason: str = "Waiting for a valid order-book snapshot"
    continuity_status: str = "RECONNECTING"
    candles: list[dict[str, Any]] = field(default_factory=list)
    candles_by_timeframe: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    candle_event_times: dict[str, float] = field(default_factory=dict)
    candle_confirmed_times: dict[str, float] = field(default_factory=dict)
    open_interest: float | None = None
    oi_change_pct: float | None = None
    oi_event_time: float | None = None
    oi_stale: bool = True
    funding_rate: float | None = None
    funding_event_time: float | None = None
    funding_stale: bool = True
    volume: float | None = None
    volume_24h: float | None = None
    volume_24h_event_time: float | None = None
    trade_event_time: float | None = None
    price_change_pct: float | None = None
    price_event_time: float | None = None
    volatility: float | None = None

    def _clean_book(self) -> None:

        self.bids = {
            price: qty
            for price, qty in self.bids.items()
            if qty > 0
        }

        self.asks = {
            price: qty
            for price, qty in self.asks.items()
            if qty > 0
        }

    def quality(self, max_age: float = 10.0, now: float | None = None, *, thresholds: dict[str, float] | None = None) -> tuple[str, str]:
        if self.data_quality == "DATA_INVALID" or self.book_invalid:
            return "DATA_INVALID", self.quality_reason
        current_time = time.time() if now is None else now
        limits = {"orderbook": max_age, "trade": max_age, "kline": max_age, "oi": 120.0, "funding": 120.0}
        if thresholds:
            limits.update(thresholds)
        component_times = {
            "orderbook": self.orderbook_event_time if self.book_ready else None,
            "trade": self.trade_event_time,
            "kline": max(self.candle_event_times.values(), default=None),
            "oi": self.oi_event_time,
            "funding": self.funding_event_time,
        }
        for name, timestamp in component_times.items():
            if timestamp is not None and current_time - timestamp > limits[name]:
                return "DATA_STALE", f"{name} data is stale"
        if self.continuity_status in {"DISCONNECTED", "RECONNECTING", "SEQUENCE_GAP", "OUT_OF_ORDER"}:
            return "DATA_INCOMPLETE", f"Feed continuity is {self.continuity_status}"
        if self.candle_event_times and not self.candle_confirmed_times:
            return "DATA_INCOMPLETE", "No confirmed candle is available"
        if not self.book_ready or self.price is None or self.open_interest is None or self.funding_rate is None:
            return "DATA_INCOMPLETE", "Required market data is unavailable"
        return "DATA_VALID", ""

    def sorted_bids(self, depth: int = 50):
        return sorted(
            self.bids.items(),
            key=lambda x: x[0],
            reverse=True,
        )[:depth]

    def sorted_asks(self, depth: int = 50):
        return sorted(
            self.asks.items(),
            key=lambda x: x[0],
        )[:depth]

    def orderbook_imbalance(
        self,
        depth: int = 20,
    ) -> float:

        bids = self.sorted_bids(depth)
        asks = self.sorted_asks(depth)

        bid_volume = sum(
            price * quantity
            for price, quantity in bids
        )

        ask_volume = sum(
            price * quantity
            for price, quantity in asks
        )

        total = bid_volume + ask_volume

        if total <= 0:
            return 0.0

        imbalance = (
            bid_volume - ask_volume
        ) / total

        # Numerical safety.
        return max(
            -1.0,
            min(1.0, imbalance),
        )

    def snapshot_bids(self, depth: int = 50):
        return [
            [price, quantity]
            for price, quantity
            in self.sorted_bids(depth)
        ]

    def snapshot_asks(self, depth: int = 50):
        return [
            [price, quantity]
            for price, quantity
            in self.sorted_asks(depth)
        ]


class BybitPublicFeed:

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        orderbook_depth: int = 50,
        stale_thresholds: dict[str, float] | None = None,
    ):

        self.symbol = symbol.upper()

        self.orderbook_depth = orderbook_depth
        self.stale_thresholds = {
            "orderbook": 30.0,
            "trade": 30.0,
            "kline": 300.0,
            "oi": 120.0,
            "funding": 120.0,
        }
        if stale_thresholds:
            self.stale_thresholds.update(stale_thresholds)

        self.data = BybitMarketData(
            symbol=self.symbol
        )

        self.running = False

        self._trade_sequence = 0
        self.oi_history = OIHistory()
        self.funding_history = FundingHistory(self.symbol)
        self.price_history = PriceHistory()
        self._reconnect_attempt = 0

    def _reset_state(self) -> None:
        """Invalidate only the book on reconnect; historical observations remain safe."""
        self.data.bids.clear()
        self.data.asks.clear()
        self.data.last_update = 0.0
        self.data.last_event_time = None
        self.data.orderbook_event_time = None
        self.data.last_sequence = None
        self.data.book_ready = False
        self.data.book_invalid = False
        self.data.data_quality = "DATA_INCOMPLETE"
        self.data.quality_reason = "Waiting for a valid order-book snapshot"
        self.data.continuity_status = "RECONNECTING"

    def _mark_disconnected(self, reason: str) -> None:
        self.data.bids.clear()
        self.data.asks.clear()
        self.data.last_sequence = None
        self.data.book_ready = False
        self.data.book_invalid = True
        self.data.data_quality = "DATA_INCOMPLETE"
        self.data.quality_reason = reason
        self.data.continuity_status = "DISCONNECTED"

    def _invalid(self, reason: str) -> None:
        self.data.data_quality = "DATA_INVALID"
        self.data.quality_reason = reason
        self.data.book_invalid = True
        self.data.book_ready = False
        if "sequence gap" in reason.lower():
            self.data.continuity_status = "SEQUENCE_GAP"
        elif "out-of-order" in reason.lower():
            self.data.continuity_status = "OUT_OF_ORDER"
        elif "sequence gap" in reason.lower():
            self.data.continuity_status = "SEQUENCE_GAP"
        else:
            self.data.continuity_status = "DEGRADED"

    def _subscription_message(self):

        return {
            "op": "subscribe",
            "args": [
                f"orderbook.{self.orderbook_depth}.{self.symbol}",
                f"publicTrade.{self.symbol}",
                *[f"kline.{interval}.{self.symbol}" for interval in (1, 3, 5, 15, 30, 60, 120, 240, "D")],
                f"tickers.{self.symbol}",
            ],
        }

    def _apply_orderbook(
        self,
        message: dict[str, Any],
        received_time: float | None = None,
    ) -> None:

        data = message.get("data")

        if not data:
            self._invalid("Missing WebSocket data payload")
            return

        sequence = data.get("u")
        if sequence is not None:
            try:
                sequence = int(sequence)
            except (TypeError, ValueError):
                self._invalid("Invalid order-book sequence")
                return
            if self.data.last_sequence is not None and sequence <= self.data.last_sequence:
                self._invalid("Out-of-order order-book update")
                return
            if self.data.last_sequence is not None and sequence > self.data.last_sequence + 1:
                self._invalid("Order-book sequence gap")
                return
        if message.get("type") != "snapshot" and not self.data.book_ready:
            self._invalid("Order-book sequence gap after reconnect")
            return
        previous_sequence = data.get("pu")
        if previous_sequence is not None and self.data.last_sequence is not None:
            try:
                if int(previous_sequence) != self.data.last_sequence:
                    self._invalid("Order-book sequence gap")
                    return
            except (TypeError, ValueError):
                self._invalid("Invalid order-book previous sequence")
                return

        def levels(key: str) -> list[tuple[float, float]] | None:
            result = []
            for level in data.get(key, []):
                if not isinstance(level, (list, tuple)) or len(level) != 2:
                    return None
                try:
                    price = float(level[0])
                    quantity = float(level[1])
                except (TypeError, ValueError):
                    return None
                if not isfinite(price) or not isfinite(quantity) or price <= 0 or quantity < 0:
                    return None
                result.append((price, quantity))
            return result

        bids = levels("b")
        asks = levels("a")
        if bids is None or asks is None:
            self._invalid("Malformed or invalid order-book level")
            return

        # -----------------------------------------
        # INITIAL SNAPSHOT
        # -----------------------------------------

        if message.get("type") == "snapshot":

            if not bids or not asks:
                self._invalid("Order-book snapshot must contain both sides")
                return

            self.data.bids.clear()
            self.data.asks.clear()

            for price, quantity in bids:

                if quantity > 0:
                    self.data.bids[
                        price
                    ] = quantity

            for price, quantity in asks:

                if quantity > 0:
                    self.data.asks[
                        price
                    ] = quantity

        # -----------------------------------------
        # DELTA UPDATE
        # -----------------------------------------

        else:

            for price, quantity in bids:

                if quantity == 0:
                    self.data.bids.pop(
                        price,
                        None,
                    )
                else:
                    self.data.bids[
                        price
                    ] = quantity

            for price, quantity in asks:

                if quantity == 0:
                    self.data.asks.pop(
                        price,
                        None,
                    )
                else:
                    self.data.asks[
                        price
                    ] = quantity

        self.data._clean_book()

        if self.data.bids and self.data.asks:
            if max(self.data.bids) >= min(self.data.asks):
                self._invalid("Order book is crossed")
                return

        if sequence is not None:
            self.data.last_sequence = sequence
        self.data.book_ready = True
        self.data.book_invalid = False
        self.data.continuity_status = "HEALTHY"
        self._reconnect_attempt = 0

        best_bid = self.data.sorted_bids(1)

        if best_bid:
            self.data.price = best_bid[0][0]

        self.data.last_update = time.time() if received_time is None else received_time
        self.data.last_event_time = float(message.get("ts", self.data.last_update * 1000)) / 1000
        self.data.orderbook_event_time = self.data.last_event_time
        self.data.data_quality = "OK"
        self.data.quality_reason = ""

    def _process_trade(
        self,
        trade: dict[str, Any],
        received_time: float | None = None,
    ) -> None:

        trade_id = str(
            trade.get(
                "i",
                f"{trade.get('T')}-{self._trade_sequence}",
            )
        )

        self._trade_sequence += 1

        # Avoid duplicate trade IDs.
        if trade_id in self.data.trade_ids:
            return

        timestamp_ms = int(trade["T"])
        event_time = timestamp_ms / 1000
        if self.data.last_trade_event_time is not None and event_time < self.data.last_trade_event_time:
            self._invalid("Out-of-order trade event")
            return
        record = {
            "id": trade_id,
            "symbol": self.symbol,
            "timestamp": timestamp_ms,
            "price": float(trade["p"]),
            "quantity": float(trade["v"]),
            "side": str(
                trade["S"]
            ).upper(),
        }

        if record["price"] <= 0 or record["quantity"] <= 0 or record["side"] not in {"BUY", "SELL"}:
            self._invalid("Invalid trade price or quantity")
            return

        self.data.price = record["price"]
        price_state = self.price_history.ingest(event_time, record["price"])
        self.data.price_change_pct = price_state.change_pct
        self.data.price_event_time = price_state.event_time
        self.data.last_trade_id = trade_id
        self.data.trade_ids.add(trade_id)
        self.data.last_trade_event_time = max(self.data.last_trade_event_time or event_time, event_time)

        self.data.trades.append(record)
        self.data.trades.sort(key=lambda item: (item["timestamp"], item["id"]))

        # Keep bounded memory.
        self.data.trades = self.data.trades[-5000:]

        self.data.last_update = time.time() if received_time is None else received_time
        self.data.last_event_time = max(self.data.last_event_time or event_time, event_time)
        self.data.trade_event_time = event_time

    def _process_message(
        self,
        message: dict[str, Any],
        received_time: float | None = None,
    ) -> None:

        topic = message.get(
            "topic",
            "",
        )

        if topic and not topic.endswith(f".{self.symbol}"):
            self._invalid("Symbol mismatch")
            return

        data = message.get("data")

        if not data:
            self._invalid("Missing WebSocket data payload")
            return

        if topic.startswith(
            "orderbook."
        ):

            self._apply_orderbook(
                message,
                received_time=received_time,
            )

        elif topic.startswith(
            "publicTrade."
        ):

            if isinstance(data, list):

                for trade in data:
                    try:
                        self._process_trade(trade, received_time=received_time)
                    except (KeyError, TypeError, ValueError):
                        self._invalid("Malformed trade payload")

        elif topic.startswith("kline."):
            if not isinstance(data, list):
                self._invalid("Malformed kline payload")
                return
            for item in data:
                try:
                    interval = normalize_bybit_interval(topic.split(".")[1])
                    candle = {
                        "timeframe": interval,
                        "event_time": float(item["start"]) / 1000,
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": float(item["close"]),
                        "volume": float(item["volume"]),
                        "confirmed": bool(item.get("confirm", True)),
                    }
                    if (candle["open"] <= 0 or candle["high"] <= 0 or candle["low"] <= 0 or candle["close"] <= 0
                            or candle["high"] < candle["low"]
                            or candle["low"] > min(candle["open"], candle["close"])
                            or candle["high"] < max(candle["open"], candle["close"])
                            or candle["volume"] < 0):
                        raise ValueError
                    timeframe = self.data.candles_by_timeframe.setdefault(interval, [])
                    timeframe[:] = [old for old in timeframe if old["event_time"] != candle["event_time"]]
                    timeframe.append(candle)
                    timeframe.sort(key=lambda old: old["event_time"])
                    del timeframe[:-500]
                    self.data.candle_event_times[interval] = candle["event_time"]
                    if candle["confirmed"]:
                        self.data.candle_confirmed_times[interval] = candle["event_time"]
                    self.data.candles = [
                        old
                        for candles in self.data.candles_by_timeframe.values()
                        for old in candles
                    ]
                    self.data.candles.sort(key=lambda old: (old["event_time"], old["timeframe"]))
                    self.data.candles = self.data.candles[-500:]
                    if candle["confirmed"]:
                        self.data.volume = candle["volume"]
                    self.data.last_event_time = candle["event_time"]
                    self.data.last_update = time.time() if received_time is None else received_time
                except (KeyError, TypeError, ValueError):
                    self._invalid("Malformed kline payload")

        elif topic.startswith("tickers."):
            if not isinstance(data, dict):
                self._invalid("Malformed ticker payload")
                return
            try:
                event_time = float(message["ts"]) / 1000 if message.get("ts") is not None else None
                if data.get("openInterest") is not None and event_time is not None:
                    state = self.oi_history.ingest(
                        event_time,
                        float(data["openInterest"]),
                    )
                    self.data.open_interest = state.open_interest
                    self.data.oi_change_pct = state.change_pct
                    self.data.oi_event_time = state.event_time
                    self.data.oi_stale = state.stale
                if data.get("fundingRate") is not None:
                    funding_rate = float(data["fundingRate"])
                    if event_time is not None:
                        funding_state = self.funding_history.ingest(event_time, funding_rate)
                        self.data.funding_rate = funding_state.funding_rate
                        self.data.funding_event_time = funding_state.event_time
                    else:
                        self.data.funding_rate = funding_rate
                        self.data.funding_event_time = None
                    self.data.funding_stale = event_time is None
                if data.get("volume24h") is not None:
                    self.data.volume_24h = float(data["volume24h"])
                    self.data.volume_24h_event_time = event_time
                if data.get("lastPrice") is not None:
                    self.data.price = float(data["lastPrice"])
                    if event_time is not None:
                        price_state = self.price_history.ingest(event_time, self.data.price)
                        self.data.price_change_pct = price_state.change_pct
                        self.data.price_event_time = price_state.event_time
                self.data.last_update = time.time() if received_time is None else received_time
                if event_time is not None:
                    self.data.last_event_time = event_time
                values = (self.data.open_interest, self.data.funding_rate, self.data.volume, self.data.volume_24h, self.data.price)
                if any(value is not None and not isfinite(value) for value in values):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                self._invalid("Malformed ticker payload")

    async def run(self) -> None:

        if websockets is None:
            raise RuntimeError(
                "The optional 'websockets' dependency is required for live feeds"
            )

        self.running = True

        print(
            "Connecting to Bybit public WebSocket..."
        )

        print(
            f"Symbol: {self.symbol}"
        )

        while self.running:

            try:

                async with websockets.connect(
                    BYBIT_PUBLIC_WS,
                    ping_interval=20,
                    ping_timeout=20,
                ) as websocket:

                    self._reset_state()

                    await websocket.send(
                        json.dumps(
                            self._subscription_message()
                        )
                    )

                    print(
                        "Connected to Bybit."
                    )

                    print(
                        "Order book + trades subscribed."
                    )

                    async for raw_message in websocket:

                        if not self.running:
                            break

                        message = json.loads(
                            raw_message
                        )

                        self._process_message(
                            message
                        )
                        if self.data.continuity_status in {"SEQUENCE_GAP", "OUT_OF_ORDER"}:
                            await websocket.close()
                            break

                    if self.running:
                        self._mark_disconnected("WebSocket stream ended")
                    self._reconnect_attempt += 1
                    await asyncio.sleep(min(30, 3 * (2 ** min(self._reconnect_attempt - 1, 3))))

            except asyncio.CancelledError:

                raise

            except Exception as exc:

                if not self.running:
                    break

                self._mark_disconnected(f"WebSocket disconnected: {type(exc).__name__}")

                print()
                print(
                    f"WebSocket error: {exc}"
                )

                print(
                    "Reconnecting in 3 seconds..."
                )

                self._reconnect_attempt += 1
                await asyncio.sleep(min(30, 3 * (2 ** min(self._reconnect_attempt - 1, 3))))

    def stop(self):
        self.running = False


async def main():

    feed = BybitPublicFeed(
        symbol="BTCUSDT",
        orderbook_depth=50,
    )

    try:

        await feed.run()

    except KeyboardInterrupt:

        print()
        print(
            "Market feed stopped."
        )

        feed.stop()


if __name__ == "__main__":
    asyncio.run(main())
