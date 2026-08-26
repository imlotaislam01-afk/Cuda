from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScannedOpportunity:
    symbol: str
    score: float
    bias: str
    setup_type: str | None
    volume_24h: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {**vars(self), "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ScanResult:
    opportunities: tuple[ScannedOpportunity, ...]
    rejected_symbols: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunities": [item.to_dict() for item in self.opportunities],
            "rejected_symbols": list(self.rejected_symbols),
        }


class MarketScanner:
    """Rank already-computed canonical market contexts without re-analysis."""

    def __init__(self, minimum_volume_24h: float = 5_000_000.0):
        if minimum_volume_24h < 0:
            raise ValueError("minimum_volume_24h must be non-negative")
        self.minimum_volume_24h = minimum_volume_24h

    @staticmethod
    def _field(item, name, default=None):
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    def scan(self, contexts) -> ScanResult:
        ranked = []
        rejected = []
        for context in contexts:
            symbol = str(self._field(context, "symbol", "")).upper()
            metadata = self._field(context, "metadata", {}) or {}
            volume = float(metadata.get("volume_24h", 0.0) or 0.0)
            if volume < self.minimum_volume_24h:
                rejected.append(symbol)
                continue
            confluence = self._field(context, "confluence")
            score = float(self._field(confluence, "score", 0.0) or 0.0)
            rvol = self._field(self._field(context, "rvol"), "rvol", 0.0) or 0.0
            score += min(20.0, max(0.0, float(rvol) - 1.0) * 10.0)
            setup = self._field(context, "setup")
            if self._field(setup, "is_setup", False):
                score += 10.0
            reasons = []
            if confluence and self._field(confluence, "bias", "WAIT") != "WAIT":
                reasons.append("DIRECTIONAL_CONFLUENCE")
            if float(rvol or 0) >= 2.0:
                reasons.append("RVOL_CONFIRMATION")
            if self._field(setup, "is_setup", False):
                reasons.append("SETUP_QUALIFIED")
            ranked.append(ScannedOpportunity(symbol, round(min(100.0, score), 2), str(self._field(context, "bias", "WAIT")), self._field(setup, "setup_type"), volume, tuple(reasons)))
        ranked.sort(key=lambda item: (-item.score, item.symbol))
        return ScanResult(tuple(ranked), tuple(rejected))
