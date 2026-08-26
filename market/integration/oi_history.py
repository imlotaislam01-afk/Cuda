from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OIState:
    event_time: float | None
    open_interest: float | None
    change_pct: float | None
    stale: bool
    velocity: float | None = None
    spike: bool = False
    compression: bool = False
    symbol: str | None = None


class OIHistory:
    """Chronological, duplicate-safe OI observations for replay and live feeds."""

    def __init__(self, stale_after: float = 120.0, symbol: str | None = None, spike_pct: float = 5.0, compression_pct: float = 0.25) -> None:
        if stale_after <= 0:
            raise ValueError("stale_after must be positive")
        if spike_pct < 0 or compression_pct < 0:
            raise ValueError("OI thresholds must be non-negative")
        self.stale_after = stale_after
        self.symbol = symbol.upper() if symbol else None
        self.spike_pct = spike_pct
        self.compression_pct = compression_pct
        self._observations: dict[float, float] = {}

    def ingest(self, event_time: float, open_interest: float, symbol: str | None = None) -> OIState:
        if symbol is not None:
            symbol = symbol.upper()
            if self.symbol is None:
                self.symbol = symbol
            elif symbol != self.symbol:
                raise ValueError("OI symbol does not match history symbol")
        event_time = float(event_time)
        open_interest = float(open_interest)
        if event_time < 0 or open_interest < 0:
            raise ValueError("OI event time and value must be non-negative")
        self._observations.setdefault(event_time, open_interest)
        return self.state(as_of=event_time)

    def state(self, as_of: float, stale_after: float | None = None) -> OIState:
        visible = sorted(
            (timestamp, value)
            for timestamp, value in self._observations.items()
            if timestamp <= as_of
        )
        if not visible:
            return OIState(None, None, None, True, symbol=self.symbol)
        timestamp, current = visible[-1]
        previous_item = visible[-2] if len(visible) > 1 else None
        previous = previous_item[1] if previous_item else None
        change = None if previous in (None, 0) else (current - previous) / abs(previous) * 100
        elapsed = timestamp - previous_item[0] if previous_item else None
        velocity = change / elapsed if change is not None and elapsed and elapsed > 0 else None
        threshold = self.stale_after if stale_after is None else stale_after
        return OIState(
            timestamp,
            current,
            change,
            as_of - timestamp > threshold,
            velocity=velocity,
            spike=change is not None and abs(change) >= self.spike_pct,
            compression=change is not None and abs(change) <= self.compression_pct,
            symbol=self.symbol,
        )