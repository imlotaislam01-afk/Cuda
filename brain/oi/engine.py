
from __future__ import annotations

from dataclasses import dataclass

from typing import Any

@dataclass(frozen=True)

class OISnapshot:

    price_change_pct: float

    oi_change_pct: float

    oi_value: float | None = None

    volume_ratio: float | None = None

    funding_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:

        return {

            "price_change_pct": self.price_change_pct,

            "oi_change_pct": self.oi_change_pct,

            "oi_value": self.oi_value,

            "volume_ratio": self.volume_ratio,

            "funding_rate": self.funding_rate,

        }

@dataclass

class OIAnalysis:

    regime: str

    direction: str

    strength: str

    price_change_pct: float

    oi_change_pct: float

    confidence: float

    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:

        return {

            "regime": self.regime,

            "direction": self.direction,

            "strength": self.strength,

            "price_change_pct": self.price_change_pct,

            "oi_change_pct": self.oi_change_pct,

            "confidence": self.confidence,

            "reasons": self.reasons,

        }

class OIEngine:

    """

    APEX Stage 8.

    Interprets price/OI relationship.

    This engine does not trade and does not

    determine final entry direction by itself.

    """

    def __init__(

        self,

        neutral_threshold_pct: float = 0.25,

        strong_threshold_pct: float = 2.0,

    ) -> None:

        if neutral_threshold_pct < 0:

            raise ValueError(

                "neutral_threshold_pct must be >= 0"

            )

        if strong_threshold_pct <= neutral_threshold_pct:

            raise ValueError(

                "strong_threshold_pct must be greater "

                "than neutral_threshold_pct"

            )

        self.neutral_threshold_pct = (

            neutral_threshold_pct

        )

        self.strong_threshold_pct = (

            strong_threshold_pct

        )

    def analyze(

        self,

        snapshot: OISnapshot,

    ) -> OIAnalysis:

        price = snapshot.price_change_pct

        oi = snapshot.oi_change_pct

        abs_price = abs(price)

        abs_oi = abs(oi)

        reasons: list[str] = []

        # -----------------------------------------------------

        # Determine OI state

        # -----------------------------------------------------

        oi_increasing = (

            oi > self.neutral_threshold_pct

        )

        oi_decreasing = (

            oi < -self.neutral_threshold_pct

        )

        price_increasing = (

            price > self.neutral_threshold_pct

        )

        price_decreasing = (

            price < -self.neutral_threshold_pct

        )

        price_flat = not (

            price_increasing

            or price_decreasing

        )

        oi_flat = not (

            oi_increasing

            or oi_decreasing

        )

        # -----------------------------------------------------

        # Classic price/OI matrix

        # -----------------------------------------------------

        if price_increasing and oi_increasing:

            regime = "LONG_BUILDUP"

            direction = "BULLISH"

            reasons.append(

                "Price rising with increasing OI"

            )

        elif price_decreasing and oi_increasing:

            regime = "SHORT_BUILDUP"

            direction = "BEARISH"

            reasons.append(

                "Price falling with increasing OI"

            )

        elif price_increasing and oi_decreasing:

            regime = "SHORT_COVERING"

            direction = "BULLISH"

            reasons.append(

                "Price rising while OI decreases"

            )

        elif price_decreasing and oi_decreasing:

            regime = "LONG_LIQUIDATION"

            direction = "BEARISH"

            reasons.append(

                "Price falling while OI decreases"

            )

        elif price_flat and oi_increasing:

            regime = "POSITION_BUILDUP"

            direction = "NEUTRAL"

            reasons.append(

                "OI increasing while price remains flat"

            )

        elif price_flat and oi_decreasing:

            regime = "POSITION_REDUCTION"

            direction = "NEUTRAL"

            reasons.append(

                "OI decreasing while price remains flat"

            )

        else:

            regime = "NEUTRAL"

            direction = "NEUTRAL"

            reasons.append(

                "Price and OI changes are neutral"

            )

        # -----------------------------------------------------

        # Strength

        # -----------------------------------------------------

        if (

            abs_oi >= self.strong_threshold_pct

            or abs_price >= self.strong_threshold_pct

        ):

            strength = "STRONG"

        elif (

            abs_oi >= self.neutral_threshold_pct

            or abs_price >= self.neutral_threshold_pct

        ):

            strength = "MODERATE"

        else:

            strength = "WEAK"

        # -----------------------------------------------------

        # Volume confirmation

        # -----------------------------------------------------

        if snapshot.volume_ratio is not None:

            if snapshot.volume_ratio >= 2.0:

                reasons.append(

                    f"High relative volume "

                    f"({snapshot.volume_ratio:.2f}x)"

                )

            elif snapshot.volume_ratio < 0.75:

                reasons.append(

                    f"Low relative volume "

                    f"({snapshot.volume_ratio:.2f}x)"

                )

        # -----------------------------------------------------

        # Funding context

        # -----------------------------------------------------

        if snapshot.funding_rate is not None:

            if snapshot.funding_rate > 0.01:

                reasons.append(

                    "Elevated positive funding"

                )

            elif snapshot.funding_rate < -0.01:

                reasons.append(

                    "Elevated negative funding"

                )

        # -----------------------------------------------------

        # Confidence

        # -----------------------------------------------------

        confidence = 50.0

        if abs_oi >= self.strong_threshold_pct:

            confidence += 20.0

        elif abs_oi >= self.neutral_threshold_pct:

            confidence += 10.0

        if abs_price >= self.strong_threshold_pct:

            confidence += 20.0

        elif abs_price >= self.neutral_threshold_pct:

            confidence += 10.0

        if snapshot.volume_ratio is not None:

            if snapshot.volume_ratio >= 2.0:

                confidence += 10.0

        confidence = min(

            100.0,

            confidence,

        )

        return OIAnalysis(

            regime=regime,

            direction=direction,

            strength=strength,

            price_change_pct=price,

            oi_change_pct=oi,

            confidence=round(

                confidence,

                2,

            ),

            reasons=reasons,

        )

