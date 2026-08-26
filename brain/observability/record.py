from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ObservabilityRecord:
    symbol: str
    event_time: float | None
    action: str
    confidence: float
    setup_type: str | None
    regime: str
    reason_codes: tuple[str, ...]
    rejected_reason: tuple[str, ...]
    evidence: dict[str, Any]
    entry: float | None = None
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    risk: dict[str, Any] | None = None
    paper_execution: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **vars(self),
            "reason_codes": list(self.reason_codes),
            "rejected_reason": list(self.rejected_reason),
            "evidence": dict(self.evidence),
        }


class ObservabilityRecorder:
    """Record final canonical decisions without changing their outcome."""

    def record(self, result) -> ObservabilityRecord:
        context = result.context
        decision = result.decision
        setup = getattr(context, "setup", None)
        evidence = {
            "structure": getattr(context, "structure", None) is not None,
            "mtf": getattr(context, "mtf", None) is not None,
            "liquidity": getattr(context, "liquidity", None) is not None,
            "orderflow": getattr(context, "orderflow", None) is not None,
            "value": getattr(context, "value", None) is not None,
            "effort": getattr(context, "effort", None) is not None,
            "fvg": getattr(context, "fvg", None) is not None,
            "order_block": getattr(context, "order_blocks", None) is not None,
        }
        reason_codes = tuple(decision.reasons)
        rejected = tuple(decision.invalidation) if not decision.is_trade else tuple(result.risk.rejection_reasons)
        return ObservabilityRecord(
            context.symbol,
            context.event_time,
            decision.action,
            decision.confidence,
            getattr(setup, "setup_type", None) or decision.setup_type,
            context.market_regime,
            reason_codes,
            rejected,
            evidence,
            decision.entry,
            decision.stop_loss,
            decision.levels.tp1,
            decision.levels.tp2,
            result.risk.to_dict() if hasattr(result.risk, "to_dict") else vars(result.risk),
            result.intent.to_dict() if getattr(result, "intent", None) is not None else None,
        )
