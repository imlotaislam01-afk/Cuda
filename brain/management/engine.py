from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PositionManagementResult:
    action: str
    stop_loss: float | None
    runner: bool
    reason: str
    event_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class PositionManagementEngine:
    """Paper-position protection decisions based on observable market facts."""

    def analyze(self, position, *, current_price: float, structure=None, effort=None, atr: float | None = None, as_of: float | None = None) -> PositionManagementResult:
        side = str(getattr(position, "action", getattr(position, "side", ""))).upper()
        entry = float(getattr(position, "entry", 0.0))
        stop = float(getattr(position, "stop_loss", getattr(position, "stop", 0.0)))
        price = float(current_price)
        if side not in {"LONG", "SHORT"} or entry <= 0 or stop <= 0 or price <= 0:
            return PositionManagementResult("EXIT", None, False, "INVALID_POSITION", as_of)
        if (side == "LONG" and price <= stop) or (side == "SHORT" and price >= stop):
            return PositionManagementResult("EXIT", stop, False, "INITIAL_STOP_INVALIDATED", as_of)
        state = str(getattr(effort, "effort_state", ""))
        if state in {"ABSORBED_BUYING", "ABSORBED_SELLING", "FAILED_EFFORT"}:
            opposing = (side == "LONG" and state == "ABSORBED_SELLING") or (side == "SHORT" and state == "ABSORBED_BUYING")
            if opposing:
                return PositionManagementResult("REDUCE", stop, False, "OPPOSING_ABSORPTION", as_of)
        trend = str(getattr(structure, "trend", ""))
        directional_effort = state in {"BULLISH_EFFORT", "BEARISH_EFFORT"} and ((side == "LONG" and state == "BULLISH_EFFORT") or (side == "SHORT" and state == "BEARISH_EFFORT"))
        if directional_effort:
            distance = float(atr or abs(entry - stop))
            breakeven = entry
            if side == "LONG":
                candidate = max(breakeven, price - distance)
                if candidate > stop:
                    return PositionManagementResult("TRAIL", candidate, True, "DIRECTIONAL_EFFORT_SUPPORTS_RUNNER", as_of)
            else:
                candidate = min(breakeven, price + distance)
                if candidate < stop:
                    return PositionManagementResult("TRAIL", candidate, True, "DIRECTIONAL_EFFORT_SUPPORTS_RUNNER", as_of)
        return PositionManagementResult("HOLD", stop, False, "NO_MANAGEMENT_TRIGGER", as_of)
