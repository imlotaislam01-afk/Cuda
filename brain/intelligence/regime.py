from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegimeResult:
    state: str
    range_pct: float | None
    directional: bool
    event_time: float | None
    as_of: float | None
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class RegimeEngine:
    """Classify visible market conditions conservatively and deterministically."""

    def __init__(self, compression_pct: float = 0.01, expansion_pct: float = 0.04):
        if compression_pct < 0 or expansion_pct <= compression_pct:
            raise ValueError("Invalid regime thresholds")
        self.compression_pct = compression_pct
        self.expansion_pct = expansion_pct

    def analyze(self, candles, *, structure=None, value=None, aggression=None, as_of=None, symbol=None) -> RegimeResult:
        visible = [
            candle for candle in candles
            if candle.get("confirmed", True)
            and (symbol is None or candle.get("symbol") in {None, symbol})
            and (as_of is None or candle.get("event_time", candle.get("timestamp")) is None
                 or float(candle.get("event_time", candle.get("timestamp"))) <= as_of)
        ]
        if not visible:
            return RegimeResult("UNKNOWN", None, False, None, as_of, ["No confirmed candles available"])
        high = max(float(candle["high"]) for candle in visible)
        low = min(float(candle["low"]) for candle in visible)
        close = float(visible[-1]["close"])
        range_pct = (high - low) / abs(close) if close else None
        value_state = getattr(value, "state", None)
        trend = getattr(structure, "trend", None)
        reasons = []
        if range_pct is None:
            return RegimeResult("UNKNOWN", None, False, visible[-1].get("event_time"), as_of, ["Invalid price range"])
        if value_state == "BALANCE":
            return RegimeResult("BALANCED", range_pct, False, visible[-1].get("event_time"), as_of, ["Value is balanced"])
        if range_pct <= self.compression_pct:
            return RegimeResult("COMPRESSION", range_pct, False, visible[-1].get("event_time"), as_of, ["Low directional range"])
        if range_pct >= self.expansion_pct:
            return RegimeResult("EXPANSION", range_pct, True, visible[-1].get("event_time"), as_of, ["Range expansion detected"])
        if trend in {"BULLISH", "BEARISH"} and value_state == "DIRECTIONAL_AUCTION":
            reasons.append("Structure and value support directional auction")
            return RegimeResult("TRENDING", range_pct, True, visible[-1].get("event_time"), as_of, reasons)
        if trend == "RANGE" or value_state in {"BALANCE", "UNAVAILABLE"}:
            return RegimeResult("CHOP", range_pct, False, visible[-1].get("event_time"), as_of, ["No directional auction confirmation"])
        return RegimeResult("UNKNOWN", range_pct, False, visible[-1].get("event_time"), as_of, ["Insufficient regime evidence"])
