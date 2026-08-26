from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReasoningResult:
    bias: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    setup_valid: bool = False


class ApexReasoner:
    """
    Deterministic reasoning layer.

    The reasoner evaluates measurable market evidence.
    The LLM will later interpret and explain this evidence,
    but it will not bypass the deterministic safety gates.
    """

    def evaluate(self, market: dict[str, Any]) -> ReasoningResult:
        score = 0.0
        reasons: list[str] = []
        warnings: list[str] = []

        structure = market.get("structure", {})
        liquidity = market.get("liquidity", {})
        order_flow = market.get("order_flow", {})
        open_interest = market.get("open_interest", {})
        volume = market.get("volume", {})

        # -----------------------------
        # MARKET STRUCTURE
        # -----------------------------

        structure_bias = structure.get("bias")

        if structure_bias == "bullish":
            score += 20
            reasons.append("Bullish market structure")

        elif structure_bias == "bearish":
            score -= 20
            reasons.append("Bearish market structure")

        # -----------------------------
        # LIQUIDITY
        # -----------------------------

        sweep = liquidity.get("sweep")

        if sweep == "sell_side":
            score += 20
            reasons.append("Sell-side liquidity sweep detected")

        elif sweep == "buy_side":
            score -= 20
            reasons.append("Buy-side liquidity sweep detected")

        # -----------------------------
        # ORDER FLOW
        # -----------------------------

        flow_bias = order_flow.get("bias")

        if flow_bias == "bullish":
            score += 20
            reasons.append("Bullish order flow")

        elif flow_bias == "bearish":
            score -= 20
            reasons.append("Bearish order flow")

        # -----------------------------
        # OPEN INTEREST
        # -----------------------------

        oi_change = open_interest.get("change_pct")

        if isinstance(oi_change, (int, float)):

            if oi_change > 3:
                reasons.append(
                    f"Open interest expanding (+{oi_change:.2f}%)"
                )

                if score > 0:
                    score += 10
                elif score < 0:
                    score -= 10

        # -----------------------------
        # VOLUME
        # -----------------------------

        rvol = volume.get("rvol")

        if isinstance(rvol, (int, float)):

            if rvol >= 3:
                reasons.append(
                    f"High relative volume ({rvol:.2f}x)"
                )

                if score > 0:
                    score += 10
                elif score < 0:
                    score -= 10

        # -----------------------------
        # FINAL BIAS
        # -----------------------------

        if score >= 50:
            bias = "LONG"

        elif score <= -50:
            bias = "SHORT"

        else:
            bias = "WAIT"

        confidence = min(abs(score), 100)

        setup_valid = (
            bias != "WAIT"
            and confidence >= 75
        )

        if confidence < 75:
            warnings.append(
                "Insufficient confluence"
            )

        return ReasoningResult(
            bias=bias,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
            setup_valid=setup_valid,
        )