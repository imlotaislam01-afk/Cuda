from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class FundingState:
    symbol: str
    event_time: float | None
    funding_rate: float | None
    stale: bool
    direction: str = "NEUTRAL"
    extreme: bool = False
    velocity: float | None = None
    acceleration: float | None = None


class FundingHistory:
    """Chronological, duplicate-safe funding observations for live and replay."""

    def __init__(self, symbol: str, stale_after: float = 120.0, extreme_positive: float = 0.01, extreme_negative: float = -0.01) -> None:
        if not symbol:
            raise ValueError("symbol is required")
        if stale_after <= 0:
            raise ValueError("stale_after must be positive")
        if extreme_negative >= extreme_positive:
            raise ValueError("Funding extreme thresholds are invalid")
        self.symbol = symbol.upper()
        self.stale_after = stale_after
        self.extreme_positive = extreme_positive
        self.extreme_negative = extreme_negative
        self._observations: dict[float, float] = {}

    def ingest(self, event_time: float, funding_rate: float) -> FundingState:
        event_time = float(event_time)
        funding_rate = float(funding_rate)
        if event_time < 0 or not isfinite(event_time):
            raise ValueError("Funding event time must be finite and non-negative")
        if not isfinite(funding_rate):
            raise ValueError("Funding rate must be finite")
        self._observations.setdefault(event_time, funding_rate)
        return self.state(as_of=event_time)

    def state(self, as_of: float, stale_after: float | None = None) -> FundingState:
        as_of = float(as_of)
        visible = sorted(
            timestamp
            for timestamp in self._observations
            if timestamp <= as_of
        )
        if not visible:
            return FundingState(self.symbol, None, None, True)
        event_time = visible[-1]
        current = self._observations[event_time]
        previous_time = visible[-2] if len(visible) > 1 else None
        previous = self._observations[previous_time] if previous_time is not None else None
        velocity = ((current - previous) / (event_time - previous_time)
                    if previous is not None and event_time > previous_time else None)
        acceleration = None
        if len(visible) > 2 and velocity is not None:
            prior_time = visible[-3]
            prior_velocity = ((previous - self._observations[prior_time]) / (previous_time - prior_time)
                              if previous_time > prior_time else None)
            if prior_velocity is not None:
                acceleration = velocity - prior_velocity
        threshold = self.stale_after if stale_after is None else stale_after
        return FundingState(
            self.symbol,
            event_time,
            current,
            as_of - event_time > threshold,
            direction="POSITIVE" if current > 0 else "NEGATIVE" if current < 0 else "NEUTRAL",
            extreme=current >= self.extreme_positive or current <= self.extreme_negative,
            velocity=velocity,
            acceleration=acceleration,
        )

    def latest(self) -> FundingState:
        if not self._observations:
            return FundingState(self.symbol, None, None, True)
        return self.state(max(self._observations))

    @property
    def observations(self) -> tuple[tuple[float, float], ...]:
        return tuple(sorted(self._observations.items()))
