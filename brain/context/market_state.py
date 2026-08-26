from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketState:

    symbol: str
    timestamp: float
    price: float

    timeframe: str = "realtime"
    regime: str = "unknown"

    structure: dict[str, Any] = field(default_factory=dict)
    liquidity: dict[str, Any] = field(default_factory=dict)

    fvg: dict[str, Any] = field(default_factory=dict)
    order_blocks: dict[str, Any] = field(default_factory=dict)

    order_flow: dict[str, Any] = field(default_factory=dict)
    orderbook: dict[str, Any] = field(default_factory=dict)

    open_interest: dict[str, Any] = field(default_factory=dict)
    funding: dict[str, Any] = field(default_factory=dict)

    volume: dict[str, Any] = field(default_factory=dict)
    volatility: dict[str, Any] = field(default_factory=dict)

    vwap: dict[str, Any] = field(default_factory=dict)
    volume_profile: dict[str, Any] = field(default_factory=dict)

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:

        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "price": self.price,
            "timeframe": self.timeframe,
            "regime": self.regime,
            "structure": self.structure,
            "liquidity": self.liquidity,
            "fvg": self.fvg,
            "order_blocks": self.order_blocks,
            "order_flow": self.order_flow,
            "orderbook": self.orderbook,
            "open_interest": self.open_interest,
            "funding": self.funding,
            "volume": self.volume,
            "volatility": self.volatility,
            "vwap": self.vwap,
            "volume_profile": self.volume_profile,
            "metadata": self.metadata,
        }
