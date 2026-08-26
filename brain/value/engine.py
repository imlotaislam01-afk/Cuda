from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market.indicators import VolumeProfileCalculator


@dataclass(frozen=True)
class ValueMigrationResult:
    poc: float | None
    vah: float | None
    val: float | None
    developing_poc: float | None
    fair_value: float | None
    migration: str
    acceptance: str
    auction: str
    state: str
    event_time: float | None
    as_of: float | None
    data_quality: str
    symbol: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "poc": self.poc,
            "vah": self.vah,
            "val": self.val,
            "developing_poc": self.developing_poc,
            "fair_value": self.fair_value,
            "migration": self.migration,
            "acceptance": self.acceptance,
            "auction": self.auction,
            "state": self.state,
            "event_time": self.event_time,
            "as_of": self.as_of,
            "data_quality": self.data_quality,
            "symbol": self.symbol,
        }


class ValueMigrationEngine:
    """Deterministic value and auction facts from visible OHLCV candles."""

    def __init__(self, lookback: int = 50, bin_size: float = 1.0, value_area_pct: float = 0.70):
        if lookback < 2:
            raise ValueError("Value lookback must be at least 2")
        self.lookback = lookback
        self.profile = VolumeProfileCalculator(lookback=lookback, bin_size=bin_size, value_area_pct=value_area_pct)

    @staticmethod
    def _visible(candles, as_of, symbol):
        visible = []
        seen = set()
        for candle in candles:
            timestamp = candle.get("event_time", candle.get("timestamp"))
            if timestamp is None or candle.get("confirmed", True) is False:
                continue
            timestamp = float(timestamp)
            if as_of is not None and timestamp > as_of:
                continue
            if symbol is not None and candle.get("symbol") not in {None, symbol}:
                continue
            if timestamp in seen:
                continue
            seen.add(timestamp)
            visible.append(candle)
        return sorted(visible, key=lambda candle: float(candle.get("event_time", candle.get("timestamp"))))

    def analyze(self, candles: list[dict[str, Any]], as_of: float | None = None, symbol: str | None = None) -> ValueMigrationResult:
        visible = self._visible(candles, as_of, symbol)
        if len(visible) < 2:
            return ValueMigrationResult(None, None, None, None, None, "UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE", None, as_of, "DATA_INCOMPLETE", symbol)

        current_profile = self.profile.calculate(visible, as_of=as_of)
        if current_profile.poc is None:
            return ValueMigrationResult(None, None, None, None, None, "UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE", float(visible[-1]["event_time"]), as_of, current_profile.data_quality, symbol)

        split = max(1, len(visible) // 2)
        prior_profile = self.profile.calculate(visible[:-split], as_of=as_of)
        developing_poc = current_profile.poc
        prior_poc = prior_profile.poc
        if prior_poc is None or developing_poc > prior_poc:
            migration = "HIGHER" if prior_poc is not None else "SIDEWAYS"
        elif developing_poc < prior_poc:
            migration = "LOWER"
        else:
            migration = "SIDEWAYS"

        close = float(visible[-1]["close"])
        if close > current_profile.vah:
            acceptance = "HIGHER"
        elif close < current_profile.val:
            acceptance = "LOWER"
        else:
            acceptance = "INSIDE_VALUE"

        if migration == "HIGHER" and acceptance == "HIGHER":
            state = auction = "DIRECTIONAL_AUCTION"
        elif migration == "LOWER" and acceptance == "LOWER":
            state = auction = "DIRECTIONAL_AUCTION"
        elif acceptance == "HIGHER":
            state, auction = "ACCEPTANCE_HIGHER", "AUCTION_HIGHER"
        elif acceptance == "LOWER":
            state, auction = "ACCEPTANCE_LOWER", "AUCTION_LOWER"
        else:
            state, auction = "BALANCE", "BALANCED_AUCTION"

        return ValueMigrationResult(
            current_profile.poc,
            current_profile.vah,
            current_profile.val,
            developing_poc,
            current_profile.poc,
            migration,
            acceptance,
            auction,
            state,
            float(visible[-1]["event_time"]),
            as_of,
            current_profile.data_quality,
            symbol,
        )
