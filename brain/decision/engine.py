from dataclasses import dataclass, field
from typing import Any

from brain.reasoning import ReasoningResult


@dataclass
class TradeDecision:
    action: str
    symbol: str
    confidence: float

    entry: float | None = None
    stop_loss: float | None = None
    take_profit: list[float] = field(default_factory=list)

    setup: str | None = None

    reasons: list[str] = field(default_factory=list)
    invalidations: list[str] = field(default_factory=list)

    execute: bool = False


class DecisionEngine:
    """
    Converts deterministic reasoning into a structured trade proposal.

    This component does NOT execute trades.
    """

    def __init__(
        self,
        min_confidence: float = 75.0,
        default_stop_distance_pct: float = 0.5,
    ):
        self.min_confidence = min_confidence
        self.default_stop_distance_pct = default_stop_distance_pct

    def build(
        self,
        market: dict[str, Any],
        reasoning: ReasoningResult,
    ) -> TradeDecision:

        symbol = market.get("symbol", "UNKNOWN")
        price = market.get("price")

        # -----------------------------------------
        # BASIC VALIDATION
        # -----------------------------------------

        if not isinstance(price, (int, float)) or price <= 0:
            return TradeDecision(
                action="WAIT",
                symbol=symbol,
                confidence=reasoning.confidence,
                reasons=reasoning.reasons,
                invalidations=["Invalid or missing market price"],
            )

        if reasoning.bias not in {"LONG", "SHORT"}:
            return TradeDecision(
                action="WAIT",
                symbol=symbol,
                confidence=reasoning.confidence,
                reasons=reasoning.reasons,
                invalidations=["No directional setup"],
            )

        if not reasoning.setup_valid:
            return TradeDecision(
                action="WAIT",
                symbol=symbol,
                confidence=reasoning.confidence,
                reasons=reasoning.reasons,
                invalidations=["Setup is not valid"],
            )

        if reasoning.confidence < self.min_confidence:
            return TradeDecision(
                action="WAIT",
                symbol=symbol,
                confidence=reasoning.confidence,
                reasons=reasoning.reasons,
                invalidations=["Confidence below minimum threshold"],
            )

        # -----------------------------------------
        # STOP LOSS
        # -----------------------------------------

        stop_distance_pct = self.default_stop_distance_pct

        if stop_distance_pct <= 0:
            return TradeDecision(
                action="WAIT",
                symbol=symbol,
                confidence=reasoning.confidence,
                reasons=reasoning.reasons,
                invalidations=["Invalid stop distance"],
            )

        distance = price * stop_distance_pct / 100.0

        # -----------------------------------------
        # LONG
        # -----------------------------------------

        if reasoning.bias == "LONG":

            stop_loss = price - distance

            take_profit = [
                price + distance * 1.5,
                price + distance * 2.0,
                price + distance * 3.0,
            ]

        # -----------------------------------------
        # SHORT
        # -----------------------------------------

        else:

            stop_loss = price + distance

            take_profit = [
                price - distance * 1.5,
                price - distance * 2.0,
                price - distance * 3.0,
            ]

        return TradeDecision(
            action=reasoning.bias,
            symbol=symbol,
            confidence=reasoning.confidence,
            entry=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            setup="APEX_CONFLUENCE",
            reasons=reasoning.reasons,
            invalidations=reasoning.warnings,
            execute=False,
        )