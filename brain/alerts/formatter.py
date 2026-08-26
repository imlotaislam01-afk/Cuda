from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AlertResult:
    text: str
    state: str
    reason_codes: tuple[str, ...]
    paper_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {**vars(self), "reason_codes": list(self.reason_codes)}


class AlertFormatter:
    """Format canonical decisions for paper-only notification channels."""

    def format(self, result) -> AlertResult:
        context = result.context
        decision = result.decision
        symbol = context.symbol
        setup = getattr(context, "setup", None)
        if decision.action not in {"LONG", "SHORT"} or result.intent is None or not result.intent.approved:
            codes = tuple(decision.invalidation or decision.reasons or ("WAIT",))
            return AlertResult(f"APEX SIGNAL\n{symbol}\nBIAS: WAIT\nREJECTED: {', '.join(codes)}\nMODE: PAPER_ONLY", "WAIT", codes)
        levels = decision.levels
        setup_type = getattr(setup, "setup_type", None) or decision.setup_type or "APEX_CONFLUENCE"
        evidence = []
        for name, value in (("STRUCTURE", context.structure), ("MTF", context.mtf), ("LIQUIDITY", context.liquidity), ("ORDERFLOW", context.orderflow), ("VALUE", context.value), ("EFFORT", context.effort), ("REGIME", context.market_regime)):
            if value is not None:
                evidence.append(name)
        text = "\n".join([
            "APEX SIGNAL", symbol, f"BIAS: {decision.action}", f"SETUP: {setup_type}",
            f"ENTRY: {levels.entry}", f"SL: {levels.stop_loss}", f"TP1: {levels.tp1}", f"TP2: {levels.tp2}",
            f"R:R: {decision.risk_reward}", f"CONFIDENCE: {decision.confidence}", f"RISK: {result.risk.risk_usd}",
            f"EVIDENCE: {', '.join(evidence)}", "ACTION: ACCEPT / CANCEL", "MODE: PAPER_ONLY",
        ])
        return AlertResult(text, "ACCEPT", tuple(evidence))
