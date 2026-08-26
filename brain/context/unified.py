from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from brain.confluence import ConfluenceResult
from brain.oi import OIAnalysis


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class Candle:
    event_time: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    confirmed: bool = True

    def __post_init__(self) -> None:
        values = {
            "event_time": self.event_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
        for name, value in values.items():
            if _finite(value, name) < 0 and name in {"event_time", "volume"}:
                raise ValueError(f"{name} must be non-negative")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("Candle OHLC bounds are invalid")


@dataclass(frozen=True)
class Trade:
    trade_id: str
    event_time: float
    price: float
    quantity: float
    side: str
    symbol: str | None = None

    def __post_init__(self) -> None:
        if not self.trade_id:
            raise ValueError("trade_id is required")
        _finite(self.event_time, "event_time")
        if _finite(self.price, "price") <= 0 or _finite(self.quantity, "quantity") <= 0:
            raise ValueError("trade price and quantity must be positive")
        if self.side.upper() not in {"BUY", "SELL"}:
            raise ValueError("trade side must be BUY or SELL")
        if self.symbol is not None and not self.symbol:
            raise ValueError("trade symbol cannot be empty")


@dataclass(frozen=True)
class OrderBook:
    bids: tuple[tuple[float, float], ...] = ()
    asks: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        for side in (self.bids, self.asks):
            for price, quantity in side:
                if _finite(price, "book price") <= 0 or _finite(quantity, "book quantity") < 0:
                    raise ValueError("book prices must be positive and quantities non-negative")
        if self.bids and self.asks and max(price for price, _ in self.bids) >= min(price for price, _ in self.asks):
            raise ValueError("order book is crossed")

    @property
    def bid(self) -> float | None:
        return max((price for price, _ in self.bids), default=None)

    @property
    def ask(self) -> float | None:
        return min((price for price, _ in self.asks), default=None)

    @property
    def spread(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    @property
    def imbalance(self) -> float:
        bid_volume = sum(price * quantity for price, quantity in self.bids)
        ask_volume = sum(price * quantity for price, quantity in self.asks)
        total = bid_volume + ask_volume
        if total <= 0:
            return 0.0
        return max(-1.0, min(1.0, (bid_volume - ask_volume) / total))


@dataclass(frozen=True)
class DataQuality:
    status: str = "OK"
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"OK", "DATA_VALID", "DATA_INVALID", "DATA_STALE", "DATA_INCOMPLETE"}:
            raise ValueError(f"Invalid data quality status: {self.status}")


@dataclass(frozen=True)
class ExchangeMetadata:
    symbol: str
    tick_size: float
    quantity_step: float
    minimum_quantity: float
    maximum_quantity: float | None = None
    contract_multiplier: float = 1.0
    price_precision: int | None = None
    quantity_precision: int | None = None

    def __post_init__(self) -> None:
        if self.tick_size <= 0 or self.quantity_step <= 0 or self.minimum_quantity < 0 or self.contract_multiplier <= 0:
            raise ValueError("Invalid exchange quantity or price metadata")
        if self.maximum_quantity is not None and self.maximum_quantity < self.minimum_quantity:
            raise ValueError("maximum_quantity cannot be below minimum_quantity")


@dataclass(frozen=True)
class PriceContext:
    symbol: str
    price: float

    timeframe: str = "5m"

    change_pct: float | None = 0.0

    volume: float | None = None
    volume_ratio: float | None = None

    atr: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "timeframe": self.timeframe,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "volume_ratio": self.volume_ratio,
            "atr": self.atr,
        }

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol is required")
        if _finite(self.price, "price") <= 0:
            raise ValueError("price must be positive")
        for name in ("change_pct", "volume", "volume_ratio"):
            value = getattr(self, name)
            if value is not None:
                _finite(value, name)
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.volume_ratio is not None and self.volume_ratio < 0:
            raise ValueError("volume_ratio must be non-negative")
        if self.atr is not None and _finite(self.atr, "atr") < 0:
            raise ValueError("atr must be non-negative")


@dataclass
class MarketContext:
    """
    Unified APEX market state.

    This is the bridge between the individual
    analysis engines and the final APEX Brain.
    """

    price: PriceContext
    exchange: str = ""

    confluence: ConfluenceResult | None = None

    oi: OIAnalysis | None = None

    orderflow: Any | None = None
    liquidity: Any | None = None
    structure: Any | None = None
    fvg: Any | None = None
    order_blocks: Any | None = None

    timestamp: float | None = None

    candles: tuple[Candle, ...] = ()
    order_book: OrderBook | None = None
    trades: tuple[Trade, ...] = ()
    delta: float = 0.0
    cvd: float = 0.0
    oi_change: float | None = None
    open_interest: float | None = None
    funding: float | None = None
    vwap: float | None = None
    volatility: float | None = None
    volatility_regime: str = "UNKNOWN"
    rvol: Any | None = None
    volume_profile: Any | None = None
    value: Any | None = None
    aggression: Any | None = None
    absorption: Any | None = None
    effort: Any | None = None
    setup: Any | None = None
    entry: Any | None = None
    pre_expansion: Any | None = None
    observability: Any | None = None
    market_regime: str = "unknown"
    microstructure: Any | None = None
    mtf: Any | None = None
    event_time: float | None = None
    received_time: float | None = None
    calculation_time: float | None = None
    data_quality: DataQuality = field(default_factory=DataQuality)
    exchange_metadata: ExchangeMetadata | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        for name in ("timestamp", "event_time", "received_time", "calculation_time"):
            value = getattr(self, name)
            if value is not None:
                _finite(value, name)
        for name in ("delta", "cvd", "oi_change"):
            value = getattr(self, name)
            if value is not None:
                _finite(value, name)
        for name in ("funding", "vwap", "volatility"):
            value = getattr(self, name)
            if value is not None:
                _finite(value, name)
        if self.event_time is not None and self.calculation_time is not None and self.calculation_time < self.event_time:
            raise ValueError("calculation_time cannot precede event_time")

    @property
    def symbol(self) -> str:
        return self.price.symbol

    @property
    def current_price(self) -> float:
        return self.price.price

    @property
    def bias(self) -> str:
        return self.confluence.bias if self.confluence else "WAIT"

    @property
    def score(self) -> float:
        return self.confluence.score if self.confluence else 0.0

    @property
    def regime(self) -> str:
        return self.oi.regime if self.oi else self.market_regime

    @property
    def oi_direction(self) -> str:
        return self.oi.direction if self.oi else "UNKNOWN"

    @property
    def trade_candidate(self) -> bool:
        return (
            self.confluence is not None
            and self.confluence.status
            == "TRADE_CANDIDATE"
        )

    @property
    def bid(self) -> float | None:
        return self.order_book.bid if self.order_book else None

    @property
    def ask(self) -> float | None:
        return self.order_book.ask if self.order_book else None

    @property
    def spread(self) -> float | None:
        return self.order_book.spread if self.order_book else None

    @property
    def data_quality_status(self) -> str:
        return self.data_quality.status

    def to_dict(self) -> dict[str, Any]:

        def serialize(value: Any) -> Any:

            if value is None:
                return None

            if hasattr(value, "to_dict"):
                return value.to_dict()

            if isinstance(value, dict):
                return {
                    k: serialize(v)
                    for k, v in value.items()
                }

            if isinstance(value, list):
                return [
                    serialize(v)
                    for v in value
                ]

            if hasattr(value, "__dict__"):
                return {
                    k: serialize(v)
                    for k, v in vars(value).items()
                }

            return value

        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "price": serialize(self.price),
            "confluence": serialize(
                self.confluence
            ),
            "oi": serialize(self.oi),
            "orderflow": serialize(
                self.orderflow
            ),
            "liquidity": serialize(
                self.liquidity
            ),
            "structure": serialize(
                self.structure
            ),
            "fvg": serialize(
                self.fvg
            ),
            "candles": serialize(self.candles),
            "order_book": serialize(self.order_book),
            "trades": serialize(self.trades),
            "delta": self.delta,
            "cvd": self.cvd,
            "oi_change": self.oi_change,
            "open_interest": self.open_interest,
            "funding": self.funding,
            "vwap": self.vwap,
            "volatility": self.volatility,
            "volatility_regime": self.volatility_regime,
            "rvol": serialize(self.rvol),
            "volume_profile": serialize(self.volume_profile),
            "value": serialize(self.value),
            "aggression": serialize(self.aggression),
            "absorption": serialize(self.absorption),
            "effort": serialize(self.effort),
            "setup": serialize(self.setup),
            "entry": serialize(self.entry),
            "pre_expansion": serialize(self.pre_expansion),
            "observability": serialize(self.observability),
            "market_regime": self.market_regime,
            "microstructure": serialize(self.microstructure),
            "mtf": serialize(self.mtf),
            "timestamp": self.timestamp,
            "event_time": self.event_time,
            "received_time": self.received_time,
            "calculation_time": self.calculation_time,
            "data_quality": serialize(self.data_quality),
            "exchange_metadata": serialize(self.exchange_metadata),
            "metadata": serialize(
                self.metadata
            ),
        }


class MarketContextBuilder:
    """
    Builder used by the APEX data pipeline.

    Individual engines can be updated independently,
    then the builder produces one immutable snapshot.
    """

    def __init__(
        self,
        symbol: str,
        price: float,
        timeframe: str = "5m",
    ) -> None:

        self._price = PriceContext(
            symbol=symbol,
            price=price,
            timeframe=timeframe,
        )
        self._exchange = ""

        self._confluence: ConfluenceResult | None = None
        self._oi: OIAnalysis | None = None

        self._orderflow: Any | None = None
        self._liquidity: Any | None = None
        self._structure: Any | None = None
        self._fvg: Any | None = None
        self._candles: tuple[Candle, ...] = ()
        self._order_book: OrderBook | None = None
        self._trades: tuple[Trade, ...] = ()
        self._delta = 0.0
        self._cvd = 0.0
        self._oi_change: float | None = None
        self._open_interest: float | None = None
        self._funding: float | None = None
        self._vwap: float | None = None
        self._volatility: float | None = None
        self._rvol: Any | None = None
        self._volume_profile: Any | None = None
        self._market_regime = "unknown"
        self._microstructure: Any | None = None
        self._mtf: Any | None = None
        self._data_quality = DataQuality()
        self._exchange_metadata: ExchangeMetadata | None = None

        self._timestamp: float | None = None
        self._event_time: float | None = None
        self._received_time: float | None = None
        self._calculation_time: float | None = None

        self._metadata: dict[str, Any] = {}

    def set_price(
        self,
        price: float,
        change_pct: float | None = None,
        volume: float | None = None,
        volume_ratio: float | None = None,
        atr: float | None = None,
    ) -> "MarketContextBuilder":

        self._price = PriceContext(
            symbol=self._price.symbol,
            price=price,
            timeframe=self._price.timeframe,
            change_pct=(
                self._price.change_pct
                if change_pct is None
                else change_pct
            ),
            volume=(
                self._price.volume
                if volume is None
                else volume
            ),
            volume_ratio=(
                self._price.volume_ratio
                if volume_ratio is None
                else volume_ratio
            ),
            atr=(
                self._price.atr
                if atr is None
                else atr
            ),
        )

        return self

    def set_price_change_pct(self, change_pct: float | None) -> "MarketContextBuilder":
        self._price = PriceContext(
            symbol=self._price.symbol,
            price=self._price.price,
            timeframe=self._price.timeframe,
            change_pct=change_pct,
            volume=self._price.volume,
            volume_ratio=self._price.volume_ratio,
            atr=self._price.atr,
        )
        return self

    def set_exchange(self, exchange: str) -> "MarketContextBuilder":
        if not exchange:
            raise ValueError("exchange is required")
        self._exchange = exchange.upper()
        return self

    def set_confluence(
        self,
        result: ConfluenceResult,
    ) -> "MarketContextBuilder":

        self._confluence = result
        return self

    def set_oi(
        self,
        result: OIAnalysis,
    ) -> "MarketContextBuilder":

        self._oi = result
        return self

    def set_orderflow(
        self,
        result: Any,
    ) -> "MarketContextBuilder":

        self._orderflow = result
        return self

    def set_liquidity(
        self,
        result: Any,
    ) -> "MarketContextBuilder":

        self._liquidity = result
        return self

    def set_structure(
        self,
        result: Any,
    ) -> "MarketContextBuilder":

        self._structure = result
        return self

    def set_fvg(
        self,
        result: Any,
    ) -> "MarketContextBuilder":

        self._fvg = result
        return self

    def set_market_data(
        self,
        *,
        candles: tuple[Candle, ...] = (),
        order_book: OrderBook | None = None,
        trades: tuple[Trade, ...] = (),
        delta: float = 0.0,
        cvd: float = 0.0,
        oi_change: float | None = None,
        open_interest: float | None = None,
        funding: float | None = None,
        vwap: float | None = None,
        volatility: float | None = None,
        rvol: Any | None = None,
        volume_profile: Any | None = None,
        market_regime: str = "unknown",
    ) -> "MarketContextBuilder":
        self._candles = tuple(candles)
        self._order_book = order_book
        self._trades = tuple(trades)
        self._delta = delta
        self._cvd = cvd
        self._oi_change = oi_change
        self._open_interest = open_interest
        self._funding = funding
        self._vwap = vwap
        self._volatility = volatility
        self._rvol = rvol
        self._volume_profile = volume_profile
        self._market_regime = market_regime
        return self

    def set_intelligence(
        self,
        *,
        microstructure: Any | None = None,
        mtf: Any | None = None,
    ) -> "MarketContextBuilder":
        self._microstructure = microstructure
        self._mtf = mtf
        return self

    def set_data_quality(
        self,
        status: str,
        reason: str = "",
    ) -> "MarketContextBuilder":
        self._data_quality = DataQuality(status, reason)
        return self

    def set_exchange_metadata(self, metadata: ExchangeMetadata) -> "MarketContextBuilder":
        if metadata.symbol != self._price.symbol:
            raise ValueError("Exchange metadata symbol does not match context")
        self._exchange_metadata = metadata
        return self

    def set_timestamp(
        self,
        timestamp: float,
    ) -> "MarketContextBuilder":

        self._timestamp = timestamp
        return self

    def add_metadata(
        self,
        key: str,
        value: Any,
    ) -> "MarketContextBuilder":

        self._metadata[key] = value
        return self

    def set_event_times(
        self,
        *,
        event_time: float | None,
        received_time: float | None = None,
        calculation_time: float | None = None,
    ) -> "MarketContextBuilder":
        self._event_time = event_time
        self._received_time = received_time
        self._calculation_time = calculation_time
        return self

    def build(self, *, allow_incomplete: bool = False) -> MarketContext:

        if self._confluence is None and not allow_incomplete:
            raise ValueError(
                "Confluence result is required"
            )

        if self._oi is None and not allow_incomplete:
            raise ValueError(
                "OI analysis is required"
            )

        return MarketContext(
            price=self._price,
            exchange=self._exchange,
            confluence=self._confluence,
            oi=self._oi,
            orderflow=self._orderflow,
            liquidity=self._liquidity,
            structure=self._structure,
            fvg=self._fvg,
            timestamp=self._timestamp,
            event_time=self._event_time,
            received_time=self._received_time,
            calculation_time=self._calculation_time,
            candles=self._candles,
            order_book=self._order_book,
            trades=self._trades,
            delta=self._delta,
            cvd=self._cvd,
            oi_change=self._oi_change,
            open_interest=self._open_interest,
            funding=self._funding,
            vwap=self._vwap,
            volatility=self._volatility,
            rvol=self._rvol,
            volume_profile=self._volume_profile,
            market_regime=self._market_regime,
            microstructure=self._microstructure,
            mtf=self._mtf,
            data_quality=self._data_quality,
            exchange_metadata=self._exchange_metadata,
            metadata=dict(self._metadata),
        )
