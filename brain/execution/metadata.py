from __future__ import annotations

import time
from dataclasses import dataclass

from brain.context.unified import ExchangeMetadata


@dataclass(frozen=True)
class MetadataSnapshot:
    metadata: ExchangeMetadata
    fetched_at: float


class ExchangeMetadataService:
    """Fetch, validate, and cache exchange instrument constraints."""

    def __init__(self, request, *, clock=time.time, max_age: float = 300.0) -> None:
        self._request = request
        self._clock = clock
        self._max_age = max_age
        self._cache: dict[tuple[str, str], MetadataSnapshot] = {}

    def get(self, exchange: str, symbol: str, *, force_refresh: bool = False) -> ExchangeMetadata:
        key = (exchange.upper(), symbol.upper())
        cached = self._cache.get(key)
        now = float(self._clock())
        if cached and not force_refresh and now - cached.fetched_at <= self._max_age:
            return cached.metadata
        metadata = self._fetch(*key)
        self._cache[key] = MetadataSnapshot(metadata, now)
        return metadata

    def _fetch(self, exchange: str, symbol: str) -> ExchangeMetadata:
        if exchange == "BINANCE":
            payload = self._request("GET", "/fapi/v1/exchangeInfo", {"symbol": symbol})
            return self._parse_binance(payload, symbol)
        if exchange == "BYBIT":
            payload = self._request("GET", "/v5/market/instruments-info", {"category": "linear", "symbol": symbol})
            return self._parse_bybit(payload, symbol)
        raise ValueError(f"Unsupported exchange metadata: {exchange}")

    @staticmethod
    def _parse_binance(payload, symbol: str) -> ExchangeMetadata:
        symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
        item = next((value for value in symbols if str(value.get("symbol", "")).upper() == symbol), None)
        if item is None:
            raise ValueError("Missing Binance instrument metadata")
        filters = {value.get("filterType"): value for value in item.get("filters", [])}
        lot = filters.get("LOT_SIZE") or filters.get("MARKET_LOT_SIZE")
        price = filters.get("PRICE_FILTER")
        if not lot or not price:
            raise ValueError("Incomplete Binance instrument metadata")
        return ExchangeMetadata(symbol, float(price["tickSize"]), float(lot["stepSize"]), float(lot["minQty"]), float(lot["maxQty"]), price_precision=_precision(price["tickSize"]), quantity_precision=_precision(lot["stepSize"]))

    @staticmethod
    def _parse_bybit(payload, symbol: str) -> ExchangeMetadata:
        values = payload.get("result", {}).get("list", []) if isinstance(payload, dict) else []
        item = next((value for value in values if str(value.get("symbol", "")).upper() == symbol), None)
        if item is None:
            raise ValueError("Missing Bybit instrument metadata")
        lot = item.get("lotSizeFilter", {})
        price = item.get("priceFilter", {})
        if not lot or not price:
            raise ValueError("Incomplete Bybit instrument metadata")
        max_qty = lot.get("maxOrderQty")
        return ExchangeMetadata(symbol, float(price["tickSize"]), float(lot["qtyStep"]), float(lot["minOrderQty"]), float(max_qty) if max_qty is not None else None, price_precision=_precision(price["tickSize"]), quantity_precision=_precision(lot["qtyStep"]))


def _precision(value: str | float) -> int:
    text = format(float(value), "f").rstrip("0").rstrip(".")
    return len(text.split(".")[1]) if "." in text else 0
