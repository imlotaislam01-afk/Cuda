from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreExpansionResult:
    state: str
    score: float
    reasons: tuple[str, ...]
    event_time: float | None
    as_of: float | None

    def to_dict(self) -> dict[str, Any]:
        return {**vars(self), "reasons": list(self.reasons)}


class PreExpansionDetector:
    """Research signal for compression and expansion pressure, never a trade."""

    def analyze(self, context, *, as_of: float | None = None) -> PreExpansionResult:
        quality = getattr(context, "data_quality_status", "OK")
        event_time = getattr(context, "event_time", None)
        if quality not in {"OK", "DATA_VALID"}:
            return PreExpansionResult("RISK_OFF", 0.0, (f"DATA_{quality}",), event_time, as_of)
        points = 0.0
        reasons = []
        rvol = getattr(getattr(context, "rvol", None), "rvol", None)
        if rvol is not None and rvol >= 1.5:
            points += 25
            reasons.append("RVOL_RISING")
        oi_change = getattr(context, "oi_change", None)
        if oi_change is not None and abs(oi_change) >= 2.0:
            points += 20
            reasons.append("OI_EXPANSION")
        regime = str(getattr(context, "market_regime", "")).upper()
        if regime in {"COMPRESSION", "CONTRACTION"}:
            points += 25
            reasons.append("COMPRESSION")
        elif regime == "EXPANSION":
            points += 20
            reasons.append("RANGE_EXPANSION")
        aggression = getattr(context, "aggression", None)
        if str(getattr(aggression, "direction", "NEUTRAL")).upper() in {"BULLISH", "BEARISH"}:
            points += 20
            reasons.append("AGGRESSIVE_FLOW")
        liquidity = getattr(context, "liquidity", None)
        if getattr(liquidity, "latest_sweep", None) is not None:
            points += 25
            reasons.append("LIQUIDITY_EVENT")
        points = min(100.0, points)
        if "LIQUIDITY_EVENT" in reasons:
            state = "LIQUIDITY_EVENT"
        elif points >= 70:
            state = "BREAKOUT_IMMINENT"
        elif points >= 40:
            state = "PRE_EXPANSION"
        else:
            state = "NORMAL"
        return PreExpansionResult(state, points, tuple(reasons), event_time, as_of)
