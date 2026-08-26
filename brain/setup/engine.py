from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SetupResult:
    setup_type: str
    direction: str
    trigger: str | None
    entry: float | None
    stop: float | None
    targets: tuple[float, ...] = ()
    invalidation: str | None = None
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    @property
    def is_setup(self) -> bool:
        return self.direction in {"LONG", "SHORT"} and self.entry is not None and self.stop is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_type": self.setup_type,
            "direction": self.direction,
            "trigger": self.trigger,
            "entry": self.entry,
            "stop": self.stop,
            "targets": list(self.targets),
            "invalidation": self.invalidation,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "reason_codes": list(self.reason_codes),
        }


class SetupEngine:
    """Classify complete, evidence-backed paper setups without executing them."""

    @staticmethod
    def _wait(*codes: str) -> SetupResult:
        return SetupResult("NONE", "WAIT", None, None, None, reason_codes=tuple(codes))

    def analyze(self, context: Any) -> SetupResult:
        if getattr(context, "data_quality_status", "OK") not in {"OK", "DATA_VALID"}:
            return self._wait("DATA_INCOMPLETE")
        price = float(getattr(context, "current_price", 0.0) or 0.0)
        structure = getattr(context, "structure", None)
        liquidity = getattr(context, "liquidity", None)
        flow = getattr(context, "orderflow", None)
        value = getattr(context, "value", None)
        mtf = getattr(context, "mtf", None)
        absorption = getattr(context, "absorption", None)
        if price <= 0 or structure is None or liquidity is None or flow is None:
            return self._wait("MISSING_CRITICAL_EVIDENCE")
        bias = str(getattr(context, "bias", "WAIT")).upper()
        flow_bias = str(getattr(flow, "bias", "")).lower()
        sweep = getattr(liquidity, "latest_sweep", None)
        sweep_ok = sweep is not None and bool(getattr(sweep, "displacement", False))
        absorbed = bool(getattr(absorption, "detected", False))
        value_state = getattr(value, "state", None)
        aligned = bool(getattr(mtf, "aligned", False)) and not bool(getattr(mtf, "conflict", False))
        direction = "LONG" if bias == "LONG" else "SHORT" if bias == "SHORT" else None
        if direction is None:
            return self._wait("NON_DIRECTIONAL_BIAS")
        matching_flow = (direction == "LONG" and flow_bias == "bullish") or (direction == "SHORT" and flow_bias == "bearish")
        if sweep_ok and absorbed and matching_flow:
            setup_type = "LIQUIDITY_SWEEP_REVERSAL"
            trigger = "confirmed_liquidity_sweep_and_rejection"
            evidence = ("LIQUIDITY_SWEEP", "ABSORPTION", "ORDERFLOW_CONFIRMATION")
        elif value_state == "DIRECTIONAL_AUCTION" and aligned and matching_flow:
            setup_type = "VALUE_MIGRATION_CONTINUATION"
            trigger = "value_acceptance_with_mtf_alignment"
            evidence = ("VALUE_MIGRATION", "MTF_ALIGNMENT", "ORDERFLOW_CONFIRMATION")
        elif getattr(structure, "bos", "NONE") in {"BULLISH", "BEARISH"} and matching_flow:
            setup_type = "BREAKOUT_CONTINUATION"
            trigger = "confirmed_break_of_structure"
            evidence = ("BOS", "ORDERFLOW_CONFIRMATION")
        else:
            return self._wait("INSUFFICIENT_SETUP_EVIDENCE")
        distance = float(getattr(context, "volatility", None) or getattr(getattr(context, "price", None), "atr", 0.0) or price * 0.005)
        if distance <= 0:
            return self._wait("INVALID_STOP_DISTANCE")
        stop = price - distance if direction == "LONG" else price + distance
        targets = (price + distance * 1.5, price + distance * 2.0) if direction == "LONG" else (price - distance * 1.5, price - distance * 2.0)
        return SetupResult(setup_type, direction, trigger, price, stop, targets, "Structure or liquidity thesis invalidated", 80.0 if len(evidence) >= 3 else 70.0, evidence, ())
