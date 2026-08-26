from dataclasses import dataclass
from typing import Any


@dataclass
class LiquiditySweep:
    detected: bool
    direction: str
    level: float | None

    sweep_price: float | None

    reclaim: bool
    rejection: bool

    strength: float

    reason: str

    @property
    def confirmed(self) -> bool:
        return self.reclaim

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "direction": self.direction,
            "level": self.level,
            "sweep_price": self.sweep_price,
            "reclaim": self.reclaim,
            "rejection": self.rejection,
            "strength": self.strength,
            "reason": self.reason,
            "confirmed": self.confirmed,
        }


class LiquiditySweepDetector:
    """
    Detects price taking a known liquidity level.

    A sweep alone is NOT an entry.
    Confirmation is required.
    """

    def detect(
        self,
        price: float,
        previous_low: float | None = None,
        previous_high: float | None = None,
        delta: float = 0.0,
        tolerance_pct: float = 0.0005,
        close: float | None = None,
    ) -> LiquiditySweep:

        if price <= 0:

            return self._none(
                "Invalid price"
            )

        # =====================================================
        # SELL-SIDE LIQUIDITY
        # =====================================================

        if previous_low is not None:

            low = float(previous_low)

            tolerance = (
                abs(low) * tolerance_pct
            )

            if price < low:

                strength = min(
                    1.0,
                    abs(price - low)
                    / max(tolerance, 1e-9),
                )

                return LiquiditySweep(
                    detected=True,
                    direction="sell_side",
                    level=low,
                    sweep_price=price,
                    reclaim=close is not None and close > low,
                    rejection=close is None or close <= low,
                    strength=strength,
                    reason=(
                        "Price traded below "
                        "previous swing low; reclaim confirmation required"
                    ),
                )

        # =====================================================
        # BUY-SIDE LIQUIDITY
        # =====================================================

        if previous_high is not None:

            high = float(previous_high)

            tolerance = (
                abs(high) * tolerance_pct
            )

            if price > high:

                strength = min(
                    1.0,
                    abs(price - high)
                    / max(tolerance, 1e-9),
                )

                return LiquiditySweep(
                    detected=True,
                    direction="buy_side",
                    level=high,
                    sweep_price=price,
                    reclaim=close is not None and close < high,
                    rejection=close is None or close >= high,
                    strength=strength,
                    reason=(
                        "Price traded above "
                        "previous swing high; reclaim confirmation required"
                    ),
                )

        return self._none(
            "No liquidity sweep"
        )

    @staticmethod
    def _none(
        reason: str,
    ) -> LiquiditySweep:

        return LiquiditySweep(
            detected=False,
            direction="none",
            level=None,
            sweep_price=None,
            reclaim=False,
            rejection=False,
            strength=0.0,
            reason=reason,
        )
