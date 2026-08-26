
from __future__ import annotations

from dataclasses import dataclass

from typing import Any

@dataclass(frozen=True)

class FairValueGap:

    """

    Three-candle imbalance / Fair Value Gap.

    Bullish FVG:

        candle[i-1].high < candle[i+1].low

    Bearish FVG:

        candle[i-1].low > candle[i+1].high

    """

    direction: str

    lower: float

    upper: float

    midpoint: float

    index: int

    size: float

    size_pct: float

    filled: bool = False

    fill_pct: float = 0.0

    creation_time: float | None = None

    symbol: str | None = None

    invalidated: bool = False

    @property

    def price(self) -> float:

        return self.midpoint

    def contains(self, price: float) -> bool:

        return self.lower <= price <= self.upper

    def to_dict(self) -> dict[str, Any]:

        return {

            "direction": self.direction,

            "lower": self.lower,

            "upper": self.upper,

            "midpoint": self.midpoint,

            "index": self.index,

            "size": self.size,

            "size_pct": self.size_pct,

            "filled": self.filled,

            "fill_pct": self.fill_pct,

            "creation_time": self.creation_time,

            "symbol": self.symbol,

            "invalidated": self.invalidated,

        }

@dataclass(frozen=True)

class Displacement:

    direction: str

    index: int

    open: float

    close: float

    high: float

    low: float

    body_size: float

    range_size: float

    body_ratio: float

    move_pct: float

    strong: bool

    def to_dict(self) -> dict[str, Any]:

        return {

            "direction": self.direction,

            "index": self.index,

            "open": self.open,

            "close": self.close,

            "high": self.high,

            "low": self.low,

            "body_size": self.body_size,

            "range_size": self.range_size,

            "body_ratio": self.body_ratio,

            "move_pct": self.move_pct,

            "strong": self.strong,

        }

@dataclass

class FVGResult:

    gaps: list[FairValueGap]

    bullish_gaps: list[FairValueGap]

    bearish_gaps: list[FairValueGap]

    displacements: list[Displacement]

    latest_fvg: FairValueGap | None

    latest_displacement: Displacement | None

    bias: str

    confidence: float

    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:

        return {

            "gaps": [x.to_dict() for x in self.gaps],

            "bullish_gaps": [

                x.to_dict()

                for x in self.bullish_gaps

            ],

            "bearish_gaps": [

                x.to_dict()

                for x in self.bearish_gaps

            ],

            "displacements": [

                x.to_dict()

                for x in self.displacements

            ],

            "latest_fvg": (

                self.latest_fvg.to_dict()

                if self.latest_fvg

                else None

            ),

            "latest_displacement": (

                self.latest_displacement.to_dict()

                if self.latest_displacement

                else None

            ),

            "bias": self.bias,

            "confidence": self.confidence,

            "reasons": self.reasons,

        }

class FVGEngine:

    """

    APEX Stage 6.

    Detects:

    1. Bullish FVGs

    2. Bearish FVGs

    3. FVG size

    4. FVG fill state

    5. Candle displacement

    6. Strong displacement

    7. Combined FVG/displacement bias

    No exchange/API dependency.

    """

    def __init__(

        self,

        min_gap_pct: float = 0.0001,

        min_body_ratio: float = 0.60,

        displacement_pct: float = 0.001,

    ) -> None:

        if min_gap_pct < 0:

            raise ValueError(

                "min_gap_pct cannot be negative"

            )

        if not 0 < min_body_ratio <= 1:

            raise ValueError(

                "min_body_ratio must be between 0 and 1"

            )

        if displacement_pct < 0:

            raise ValueError(

                "displacement_pct cannot be negative"

            )

        self.min_gap_pct = min_gap_pct

        self.min_body_ratio = min_body_ratio

        self.displacement_pct = displacement_pct

    # =========================================================

    # HELPERS

    # =========================================================

    @staticmethod

    def _open(candle: dict[str, Any]) -> float:

        return float(candle.get("open", candle["close"]))

    @staticmethod

    def _high(candle: dict[str, Any]) -> float:

        return float(candle["high"])

    @staticmethod

    def _low(candle: dict[str, Any]) -> float:

        return float(candle["low"])

    @staticmethod

    def _close(candle: dict[str, Any]) -> float:

        return float(candle["close"])

    # =========================================================

    # FVG DETECTION

    # =========================================================

    def detect_fvgs(

        self,

        candles: list[dict[str, Any]],
        as_of: float | None = None,
        symbol: str | None = None,

    ) -> list[FairValueGap]:

        gaps: list[FairValueGap] = []
        candles = [
            candle for candle in candles
            if candle.get("confirmed", True)
            and (symbol is None or candle.get("symbol") in {None, symbol})
            and (
                as_of is None
                or candle.get("event_time", candle.get("timestamp")) is None
                or float(candle.get("event_time", candle.get("timestamp"))) <= as_of
            )
        ]

        if len(candles) < 3:

            return gaps

        for i in range(1, len(candles) - 1):

            left = candles[i - 1]

            right = candles[i + 1]

            left_high = self._high(left)

            left_low = self._low(left)

            right_high = self._high(right)

            right_low = self._low(right)

            # -------------------------------------------------

            # BULLISH FVG

            # -------------------------------------------------

            if left_high < right_low:

                lower = left_high

                upper = right_low

                size = upper - lower

                reference = max(

                    abs(lower),

                    1e-12,

                )

                size_pct = size / reference

                if size_pct >= self.min_gap_pct:

                    gaps.append(

                        FairValueGap(

                            direction="BULLISH",

                            lower=lower,

                            upper=upper,

                            midpoint=(lower + upper) / 2,

                            index=i,

                            size=size,

                            size_pct=size_pct,

                            creation_time=right.get("event_time", right.get("timestamp")),

                            symbol=symbol or right.get("symbol"),

                        )

                    )

            # -------------------------------------------------

            # BEARISH FVG

            # -------------------------------------------------

            elif left_low > right_high:

                lower = right_high

                upper = left_low

                size = upper - lower

                reference = max(

                    abs(lower),

                    1e-12,

                )

                size_pct = size / reference

                if size_pct >= self.min_gap_pct:

                    gaps.append(

                        FairValueGap(

                            direction="BEARISH",

                            lower=lower,

                            upper=upper,

                            midpoint=(lower + upper) / 2,

                            index=i,

                            size=size,

                            size_pct=size_pct,

                            creation_time=right.get("event_time", right.get("timestamp")),

                            symbol=symbol or right.get("symbol"),

                        )

                    )

        return gaps

    # =========================================================

    # FVG FILL DETECTION

    # =========================================================

    def update_fvg_fills(

        self,

        candles: list[dict[str, Any]],

        gaps: list[FairValueGap],
        as_of: float | None = None,

    ) -> list[FairValueGap]:

        updated: list[FairValueGap] = []

        for gap in gaps:

            max_fill = 0.0

            for i in range(

                gap.index + 2,

                len(candles),

            ):

                candle = candles[i]
                timestamp = candle.get("event_time", candle.get("timestamp"))
                if candle.get("confirmed", True) is False:
                    continue
                if as_of is not None and timestamp is not None and float(timestamp) > as_of:
                    continue

                low = self._low(candle)

                high = self._high(candle)

                if gap.direction == "BULLISH":

                    if low <= gap.lower:

                        max_fill = 1.0

                        break

                    if low < gap.upper:

                        penetrated = (

                            gap.upper - low

                        )

                        max_fill = max(

                            max_fill,

                            min(

                                1.0,

                                penetrated / gap.size,

                            ),

                        )

                else:

                    if high >= gap.upper:

                        max_fill = 1.0

                        break

                    if high > gap.lower:

                        penetrated = (

                            high - gap.lower

                        )

                        max_fill = max(

                            max_fill,

                            min(

                                1.0,

                                penetrated / gap.size,

                            ),

                        )

            updated.append(

                FairValueGap(

                    direction=gap.direction,

                    lower=gap.lower,

                    upper=gap.upper,

                    midpoint=gap.midpoint,

                    index=gap.index,

                    size=gap.size,

                    size_pct=gap.size_pct,
                    creation_time=gap.creation_time,
                    symbol=gap.symbol,
                    filled=max_fill >= 1.0,

                    fill_pct=max_fill,
                    invalidated=max_fill >= 1.0,

                )

            )

        return updated

    # =========================================================

    # DISPLACEMENT

    # =========================================================

    def detect_displacements(

        self,

        candles: list[dict[str, Any]],
        as_of: float | None = None,

    ) -> list[Displacement]:

        results: list[Displacement] = []
        if as_of is not None:
            candles = [
                candle for candle in candles
                if candle.get("confirmed", True)
                if candle.get("event_time", candle.get("timestamp")) is None
                or float(candle.get("event_time", candle.get("timestamp"))) <= as_of
            ]

        for index, candle in enumerate(candles):

            open_ = self._open(candle)

            high = self._high(candle)

            low = self._low(candle)

            close = self._close(candle)

            range_size = high - low

            if range_size <= 0:

                continue

            body_size = abs(close - open_)

            body_ratio = (

                body_size / range_size

            )

            move_pct = (

                abs(close - open_)

                / max(abs(open_), 1e-12)

            )

            if close > open_:

                direction = "BULLISH"

            elif close < open_:

                direction = "BEARISH"

            else:

                direction = "NONE"

            strong = (

                direction != "NONE"

                and body_ratio >= self.min_body_ratio

                and move_pct >= self.displacement_pct

            )

            results.append(

                Displacement(

                    direction=direction,

                    index=index,

                    open=open_,

                    close=close,

                    high=high,

                    low=low,

                    body_size=body_size,

                    range_size=range_size,

                    body_ratio=body_ratio,

                    move_pct=move_pct,

                    strong=strong,

                )

            )

        return results

    # =========================================================

    # MAIN ANALYSIS

    # =========================================================

    def analyze(

        self,

        candles: list[dict[str, Any]],
        as_of: float | None = None,
        symbol: str | None = None,

    ) -> FVGResult:

        if not candles:

            return FVGResult(

                gaps=[],

                bullish_gaps=[],

                bearish_gaps=[],

                displacements=[],

                latest_fvg=None,

                latest_displacement=None,

                bias="WAIT",

                confidence=0.0,

                reasons=[],

            )

        visible_candles = [
            candle for candle in candles
            if candle.get("confirmed", True)
            and (symbol is None or candle.get("symbol") in {None, symbol})
            if as_of is None
            or candle.get("event_time", candle.get("timestamp")) is None
            or float(candle.get("event_time", candle.get("timestamp"))) <= as_of
        ]
        gaps = self.detect_fvgs(visible_candles, symbol=symbol)

        gaps = self.update_fvg_fills(

            visible_candles,

            gaps,

        )

        displacements = (

            self.detect_displacements(visible_candles)

        )

        bullish_gaps = [

            x for x in gaps

            if x.direction == "BULLISH"

            and not x.filled

        ]

        bearish_gaps = [

            x for x in gaps

            if x.direction == "BEARISH"

            and not x.filled

        ]

        latest_fvg = (

            gaps[-1]

            if gaps

            else None

        )

        strong_displacements = [

            x for x in displacements

            if x.strong

        ]

        latest_displacement = (

            strong_displacements[-1]

            if strong_displacements

            else None

        )

        reasons: list[str] = []

        if bullish_gaps:

            reasons.append(

                f"{len(bullish_gaps)} active bullish FVG(s)"

            )

        if bearish_gaps:

            reasons.append(

                f"{len(bearish_gaps)} active bearish FVG(s)"

            )

        if latest_displacement is not None:

            reasons.append(

                f"Strong {latest_displacement.direction.lower()} displacement"

            )

        bias = "WAIT"

        confidence = 0.0

        if latest_displacement is not None:

            if (

                latest_displacement.direction == "BULLISH"

                and bullish_gaps

            ):

                bias = "LONG"

                confidence = 85.0

                reasons.append(

                    "Bullish displacement aligned with bullish FVG"

                )

            elif (

                latest_displacement.direction == "BEARISH"

                and bearish_gaps

            ):

                bias = "SHORT"

                confidence = 85.0

                reasons.append(

                    "Bearish displacement aligned with bearish FVG"

                )

            elif (

                latest_displacement.direction == "BULLISH"

            ):

                bias = "LONG"

                confidence = 60.0

            elif (

                latest_displacement.direction == "BEARISH"

            ):

                bias = "SHORT"

                confidence = 60.0

        return FVGResult(

            gaps=gaps,

            bullish_gaps=bullish_gaps,

            bearish_gaps=bearish_gaps,

            displacements=displacements,

            latest_fvg=latest_fvg,

            latest_displacement=latest_displacement,

            bias=bias,

            confidence=confidence,

            reasons=reasons,

        )

