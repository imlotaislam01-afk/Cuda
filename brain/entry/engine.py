from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EntryResult:
    direction: str
    entry: float | None
    stop_loss: float | None
    tp1: float | None
    tp2: float | None
    invalidation: str | None
    risk_reward: float | None
    confidence: float
    setup_type: str
    reason_codes: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.direction in {"LONG", "SHORT"} and self.entry is not None and self.stop_loss is not None and self.risk_reward is not None

    def to_dict(self) -> dict[str, Any]:
        return {**vars(self), "reason_codes": list(self.reason_codes), "valid": self.valid}


class EntryEngine:
    """Validate setup-derived hypothetical levels; never submits orders."""

    def analyze(self, setup) -> EntryResult:
        if not getattr(setup, "is_setup", False):
            return EntryResult("WAIT", None, None, None, None, None, None, 0.0, "NONE", ("INVALID_SETUP",))
        direction = setup.direction
        entry = float(setup.entry)
        stop = float(setup.stop)
        targets = tuple(float(target) for target in setup.targets)
        if entry <= 0 or stop <= 0 or (direction == "LONG" and stop >= entry) or (direction == "SHORT" and stop <= entry):
            return EntryResult("WAIT", None, None, None, None, "Invalid structural stop", None, 0.0, setup.setup_type, ("INVALID_STOP",))
        if not targets or (direction == "LONG" and targets[0] <= entry) or (direction == "SHORT" and targets[0] >= entry):
            return EntryResult("WAIT", None, None, None, None, "No defensible target", None, 0.0, setup.setup_type, ("INVALID_TARGET",))
        risk_reward = abs(targets[0] - entry) / abs(entry - stop)
        return EntryResult(direction, entry, stop, targets[0], targets[1] if len(targets) > 1 else None, setup.invalidation, risk_reward, setup.confidence, setup.setup_type)
