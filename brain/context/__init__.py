from .unified import (
    Candle,
    DataQuality,
    ExchangeMetadata,
    MarketContext,
    MarketContextBuilder,
    OrderBook,
    PriceContext,
    Trade,
)


def build_context(state) -> dict:
    """Compatibility adapter for the legacy dictionary reasoner."""
    if not hasattr(state, "to_dict"):
        raise TypeError("state must provide to_dict()")
    return {"market": state.to_dict(), "state": state}

__all__ = [
    "MarketContext",
    "MarketContextBuilder",
    "PriceContext",
    "Candle",
    "Trade",
    "OrderBook",
    "DataQuality",
    "ExchangeMetadata",
    "build_context",
]
