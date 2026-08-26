from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ACTIVE_STATES = {"ACTIVE", "PARTIALLY_MITIGATED"}


@dataclass(frozen=True)
class OrderBlock:
    symbol: str | None
    direction: str
    origin_time: float
    upper: float
    lower: float
    creation_time: float
    mitigation_state: str
    invalidation_state: str
    event_time: float

    @property
    def active(self) -> bool:
        return self.mitigation_state in ACTIVE_STATES and self.invalidation_state != "INVALIDATED"

    def to_dict(self) -> dict[str, Any]:
        return {**vars(self), "active": self.active}


@dataclass(frozen=True)
class OrderBlockResult:
    blocks: list[OrderBlock]
    bullish_blocks: list[OrderBlock]
    bearish_blocks: list[OrderBlock]
    latest: OrderBlock | None
    bias: str
    confidence: float
    reasons: list[str]

    @property
    def active(self) -> bool:
        return any(block.active for block in self.blocks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocks": [block.to_dict() for block in self.blocks],
            "bullish_blocks": [block.to_dict() for block in self.bullish_blocks],
            "bearish_blocks": [block.to_dict() for block in self.bearish_blocks],
            "latest": self.latest.to_dict() if self.latest else None,
            "active": self.active,
            "bias": self.bias,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
        }


class OrderBlockEngine:
    """Detect and track order blocks from confirmed, visible candles only."""

    def __init__(self, min_body_ratio: float = 0.6, min_move_pct: float = 0.001) -> None:
        self.min_body_ratio = min_body_ratio
        self.min_move_pct = min_move_pct

    @staticmethod
    def _time(candle: dict[str, Any]) -> float | None:
        value = candle.get("event_time", candle.get("timestamp"))
        return None if value is None else float(value)

    def analyze(
        self,
        candles: list[dict[str, Any]],
        *,
        as_of: float | None = None,
        symbol: str | None = None,
    ) -> OrderBlockResult:
        visible = [
            candle for candle in candles
            if candle.get("confirmed", True)
            and (symbol is None or candle.get("symbol") in {None, symbol})
            and (self._time(candle) is None or as_of is None or self._time(candle) <= as_of)
        ]
        blocks: list[OrderBlock] = []
        for index in range(1, len(visible)):
            origin = visible[index - 1]
            displacement = visible[index]
            origin_time = self._time(origin)
            creation_time = self._time(displacement)
            if origin_time is None or creation_time is None:
                continue
            high = float(displacement["high"])
            low = float(displacement["low"])
            opening = float(displacement.get("open", displacement["close"]))
            closing = float(displacement["close"])
            span = high - low
            if span <= 0 or abs(closing - opening) / span < self.min_body_ratio:
                continue
            if abs(closing - opening) / max(abs(opening), 1e-12) < self.min_move_pct:
                continue
            direction = "BULLISH" if closing > opening else "BEARISH"
            origin_open = float(origin.get("open", origin["close"]))
            origin_close = float(origin["close"])
            if direction == "BULLISH" and origin_close >= origin_open:
                continue
            if direction == "BEARISH" and origin_close <= origin_open:
                continue
            lower = float(origin["low"])
            upper = max(origin_open, origin_close)
            if direction == "BEARISH":
                lower = min(origin_open, origin_close)
                upper = float(origin["high"])
            state = "ACTIVE"
            invalidation = "VALID"
            for later in visible[index + 1:]:
                later_low = float(later["low"])
                later_high = float(later["high"])
                touched = later_low <= upper and later_high >= lower
                invalidated = later_low < lower if direction == "BULLISH" else later_high > upper
                if invalidated:
                    state, invalidation = "INVALIDATED", "INVALIDATED"
                    break
                if touched:
                    state = "MITIGATED" if (later_low <= lower if direction == "BULLISH" else later_high >= upper) else "PARTIALLY_MITIGATED"
            blocks.append(OrderBlock(symbol, direction, origin_time, upper, lower, creation_time, state, invalidation, creation_time))
        active = [block for block in blocks if block.active]
        latest = blocks[-1] if blocks else None
        bias = "WAIT"
        if active:
            bias = "LONG" if active[-1].direction == "BULLISH" else "SHORT"
        return OrderBlockResult(
            blocks=blocks,
            bullish_blocks=[block for block in blocks if block.direction == "BULLISH"],
            bearish_blocks=[block for block in blocks if block.direction == "BEARISH"],
            latest=latest,
            bias=bias,
            confidence=80.0 if active else 0.0,
            reasons=[f"{len(active)} active order block(s)"] if active else [],
        )