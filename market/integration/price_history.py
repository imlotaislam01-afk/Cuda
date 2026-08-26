from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceState:
    event_time: float | None
    price: float | None
    change_pct: float | None


class PriceHistory:
    """Deterministic event-time price observations for live state and replay."""

    def __init__(self) -> None:
        self._observations: dict[float, float] = {}

    def ingest(self, event_time: float, price: float) -> PriceState:
        event_time = float(event_time)
        price = float(price)
        if event_time < 0 or price <= 0:
            raise ValueError("Price event time must be non-negative and price positive")
        self._observations.setdefault(event_time, price)
        return self.state(event_time)

    def state(self, as_of: float | None = None) -> PriceState:
        visible = sorted(
            (timestamp, price)
            for timestamp, price in self._observations.items()
            if as_of is None or timestamp <= as_of
        )
        if not visible:
            return PriceState(None, None, None)
        timestamp, current = visible[-1]
        previous = visible[-2][1] if len(visible) > 1 else None
        change = None if previous is None else (current - previous) / previous * 100
        return PriceState(timestamp, current, change)

    @property
    def observations(self) -> tuple[tuple[float, float], ...]:
        return tuple(sorted(self._observations.items()))
