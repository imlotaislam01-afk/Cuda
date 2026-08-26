from dataclasses import dataclass
from typing import Any


@dataclass
class MicrostructureSignal:
    bias: str
    score: float

    delta_bias: str
    book_bias: str

    sweep: str
    sweep_strength: float

    absorption: bool
    divergence: bool

    aggression: str

    reasons: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bias": self.bias,
            "score": self.score,
            "delta_bias": self.delta_bias,
            "book_bias": self.book_bias,
            "sweep": self.sweep,
            "sweep_strength": self.sweep_strength,
            "absorption": self.absorption,
            "divergence": self.divergence,
            "aggression": self.aggression,
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


class MicrostructureEngine:
    """
    Converts raw order-flow and liquidity information
    into a deterministic microstructure signal.

    This module does NOT execute trades.
    """

    def analyze(
        self,
        market: dict[str, Any],
    ) -> MicrostructureSignal:

        flow = market.get("order_flow") or {}
        book = market.get("orderbook") or {}
        liquidity = market.get("liquidity") or {}

        long_score = 0.0
        short_score = 0.0

        reasons: list[str] = []
        warnings: list[str] = []

        # =====================================================
        # DELTA
        # =====================================================

        delta = float(
            flow.get("delta", 0.0) or 0.0
        )

        if delta > 0:

            delta_bias = "bullish"

            long_score += 20

            reasons.append(
                "Positive aggressive delta"
            )

        elif delta < 0:

            delta_bias = "bearish"

            short_score += 20

            reasons.append(
                "Negative aggressive delta"
            )

        else:

            delta_bias = "neutral"

        # =====================================================
        # AGGRESSION
        # =====================================================

        aggression = str(
            flow.get(
                "aggression",
                "none",
            )
        ).lower()

        if aggression == "strong":

            if delta > 0:

                long_score += 10

                reasons.append(
                    "Strong buy-side aggression"
                )

            elif delta < 0:

                short_score += 10

                reasons.append(
                    "Strong sell-side aggression"
                )

        # =====================================================
        # ORDER BOOK
        # =====================================================

        imbalance = float(
            book.get(
                "imbalance",
                0.0,
            ) or 0.0
        )

        # Safety clamp.
        imbalance = max(
            -1.0,
            min(1.0, imbalance),
        )

        if imbalance >= 0.20:

            book_bias = "bullish"

            long_score += 20

            reasons.append(
                "Bid-side order-book dominance"
            )

        elif imbalance <= -0.20:

            book_bias = "bearish"

            short_score += 20

            reasons.append(
                "Ask-side order-book dominance"
            )

        else:

            book_bias = "neutral"

        # =====================================================
        # LIQUIDITY SWEEP
        # =====================================================

        sweep = str(
            liquidity.get(
                "sweep",
                "none",
            )
        ).lower()

        sweep_strength = float(
            liquidity.get(
                "sweep_strength",
                0.0,
            ) or 0.0
        )

        sweep_strength = max(
            0.0,
            min(1.0, sweep_strength),
        )

        if sweep == "sell_side":

            long_score += 25

            reasons.append(
                "Sell-side liquidity sweep detected"
            )

        elif sweep == "buy_side":

            short_score += 25

            reasons.append(
                "Buy-side liquidity sweep detected"
            )

        # =====================================================
        # ABSORPTION
        # =====================================================

        absorption = bool(
            flow.get(
                "absorption",
                False,
            )
        )

        if absorption:

            if delta > 0:

                long_score += 10

                reasons.append(
                    "Aggressive buying shows absorption"
                )

            elif delta < 0:

                short_score += 10

                reasons.append(
                    "Aggressive selling shows absorption"
                )

            else:

                warnings.append(
                    "Absorption detected without directional delta"
                )

        # =====================================================
        # CVD
        # =====================================================

        cvd = float(
            flow.get(
                "cumulative_delta",
                0.0,
            ) or 0.0
        )

        # =====================================================
        # CVD / ORDER-BOOK DIVERGENCE
        # =====================================================

        divergence = False

        if cvd > 0 and imbalance < -0.30:

            divergence = True

            reasons.append(
                "Positive CVD vs negative order-book imbalance"
            )

        elif cvd < 0 and imbalance > 0.30:

            divergence = True

            reasons.append(
                "Negative CVD vs positive order-book imbalance"
            )

        # Divergence is context, not an automatic trade.
        if divergence:

            warnings.append(
                "Order-flow and resting-liquidity conflict"
            )

        # =====================================================
        # ROLLING FLOW
        # =====================================================

        rolling = flow.get(
            "rolling",
            {},
        ) or {}

        short_window = (
            rolling.get("5")
            or rolling.get(5)
            or {}
        )

        short_delta = float(
            short_window.get(
                "delta",
                0.0,
            ) or 0.0
        )

        if short_delta > 0 and delta < 0:

            warnings.append(
                "Short-term delta improving against current delta"
            )

        elif short_delta < 0 and delta > 0:

            warnings.append(
                "Short-term delta weakening against current delta"
            )

        # =====================================================
        # FINAL BIAS
        # =====================================================

        if long_score > short_score:

            bias = "LONG"

            score = long_score

        elif short_score > long_score:

            bias = "SHORT"

            score = short_score

        else:

            bias = "WAIT"

            score = 0.0

        return MicrostructureSignal(
            bias=bias,
            score=min(100.0, score),

            delta_bias=delta_bias,
            book_bias=book_bias,

            sweep=sweep,
            sweep_strength=sweep_strength,

            absorption=absorption,
            divergence=divergence,

            aggression=aggression,

            reasons=reasons,
            warnings=warnings,
        )
