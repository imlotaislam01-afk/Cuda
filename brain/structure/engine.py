
from dataclasses import dataclass

from typing import Any

@dataclass

class SwingPoint:

    index: int

    price: float

    kind: str

    def to_dict(self) -> dict[str, Any]:

        return {

            "index": self.index,

            "price": self.price,

            "kind": self.kind,

        }

@dataclass

class StructureEvent:

    event: str

    direction: str

    price: float

    reference: float | None

    index: int

    def to_dict(self) -> dict[str, Any]:

        return {

            "event": self.event,

            "direction": self.direction,

            "price": self.price,

            "reference": self.reference,

            "index": self.index,

        }

@dataclass

class StructureResult:

    bias: str

    strength: float

    trend: str

    last_high: float | None

    last_low: float | None

    previous_high: float | None

    previous_low: float | None

    higher_high: bool

    higher_low: bool

    lower_high: bool

    lower_low: bool

    bos: str

    choch: str

    swings: list[SwingPoint]

    events: list[StructureEvent]

    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:

        return {

            "bias": self.bias,

            "strength": self.strength,

            "trend": self.trend,

            "last_high": self.last_high,

            "last_low": self.last_low,

            "previous_high": self.previous_high,

            "previous_low": self.previous_low,

            "higher_high": self.higher_high,

            "higher_low": self.higher_low,

            "lower_high": self.lower_high,

            "lower_low": self.lower_low,

            "bos": self.bos,

            "choch": self.choch,

            "swings": [

                x.to_dict() for x in self.swings

            ],

            "events": [

                x.to_dict() for x in self.events

            ],

            "reasons": self.reasons,

        }

class MarketStructureEngine:

    def __init__(self, swing_strength: int = 2):

        if swing_strength < 1:

            raise ValueError(

                "swing_strength must be >= 1"

            )

        self.swing_strength = swing_strength

    @staticmethod
    def _visible_candles(candles, as_of, symbol=None):
        return [
            candle for candle in candles
            if candle.get("confirmed", True)
            and (symbol is None or candle.get("symbol") in {None, symbol})
            and (
                as_of is None
                or candle.get("event_time", candle.get("timestamp")) is None
                or float(candle.get("event_time", candle.get("timestamp"))) <= as_of
            )
        ]

    # =========================================================

    # SWINGS

    # =========================================================

    def detect_swings(

        self,

        candles: list[dict[str, Any]],
        as_of: float | None = None,
        symbol: str | None = None,

    ) -> list[SwingPoint]:

        candles = self._visible_candles(candles, as_of, symbol)

        s = self.swing_strength

        n = len(candles)

        if n < (2 * s + 1):

            return []

        swings: list[SwingPoint] = []

        for i in range(s, n - s):

            high = float(candles[i]["high"])

            low = float(candles[i]["low"])

            left = candles[i - s:i]

            right = candles[i + 1:i + s + 1]

            left_high = max(

                float(x["high"]) for x in left

            )

            right_high = max(

                float(x["high"]) for x in right

            )

            left_low = min(

                float(x["low"]) for x in left

            )

            right_low = min(

                float(x["low"]) for x in right

            )

            if (

                high > left_high

                and high >= right_high

            ):

                swings.append(

                    SwingPoint(

                        index=i,

                        price=high,

                        kind="HIGH",

                    )

                )

            if (

                low < left_low

                and low <= right_low

            ):

                swings.append(

                    SwingPoint(

                        index=i,

                        price=low,

                        kind="LOW",

                    )

                )

        swings.sort(

            key=lambda x: x.index

        )

        return swings

    # =========================================================

    # ANALYSIS

    # =========================================================

    def analyze(

        self,

        candles: list[dict[str, Any]],
        as_of: float | None = None,
        symbol: str | None = None,

    ) -> StructureResult:

        candles = self._visible_candles(candles, as_of, symbol)

        swings = self.detect_swings(candles, symbol=symbol)

        highs = [

            x for x in swings

            if x.kind == "HIGH"

        ]

        lows = [

            x for x in swings

            if x.kind == "LOW"

        ]

        last_high = (

            highs[-1].price

            if highs else None

        )

        previous_high = (

            highs[-2].price

            if len(highs) >= 2

            else None

        )

        last_low = (

            lows[-1].price

            if lows else None

        )

        previous_low = (

            lows[-2].price

            if len(lows) >= 2

            else None

        )

        higher_high = (

            last_high is not None

            and previous_high is not None

            and last_high > previous_high

        )

        lower_high = (

            last_high is not None

            and previous_high is not None

            and last_high < previous_high

        )

        higher_low = (

            last_low is not None

            and previous_low is not None

            and last_low > previous_low

        )

        lower_low = (

            last_low is not None

            and previous_low is not None

            and last_low < previous_low

        )

        # =====================================================

        # TREND

        # =====================================================

        if higher_high and higher_low:

            trend = "BULLISH"

        elif lower_high and lower_low:

            trend = "BEARISH"

        else:

            trend = "RANGE"

        # =====================================================

        # CURRENT PRICE

        # =====================================================

        if not candles:

            current_price = None

        else:

            current_price = float(

                candles[-1]["close"]

            )

        # =====================================================

        # CONFIRMED SWINGS

        # =========================================================

        current_index = len(candles) - 1

        confirmed_highs = [

            x for x in highs

            if x.index < current_index

        ]

        confirmed_lows = [

            x for x in lows

            if x.index < current_index

        ]

        reference_high = (

            confirmed_highs[-1].price

            if confirmed_highs

            else None

        )

        reference_low = (

            confirmed_lows[-1].price

            if confirmed_lows

            else None

        )

        # =====================================================

        # BOS

        # =====================================================

        bos = "NONE"

        events: list[StructureEvent] = []

        if current_price is not None:

            if (

                reference_high is not None

                and current_price > reference_high

            ):

                bos = "BULLISH"

                events.append(

                    StructureEvent(

                        event="BOS",

                        direction="BULLISH",

                        price=current_price,

                        reference=reference_high,

                        index=current_index,

                    )

                )

            elif (

                reference_low is not None

                and current_price < reference_low

            ):

                bos = "BEARISH"

                events.append(

                    StructureEvent(

                        event="BOS",

                        direction="BEARISH",

                        price=current_price,

                        reference=reference_low,

                        index=current_index,

                    )

                )

        # =====================================================

        # CHOCH

        # =====================================================

        choch = "NONE"

        if (

            bos == "BULLISH"

            and trend == "BEARISH"

        ):

            choch = "BULLISH"

            events.append(

                StructureEvent(

                    event="CHOCH",

                    direction="BULLISH",

                    price=current_price,

                    reference=reference_high,

                    index=current_index,

                )

            )

        elif (

            bos == "BEARISH"

            and trend == "BULLISH"

        ):

            choch = "BEARISH"

            events.append(

                StructureEvent(

                    event="CHOCH",

                    direction="BEARISH",

                    price=current_price,

                    reference=reference_low,

                    index=current_index,

                )

            )

        # =====================================================

        # BIAS

        # =====================================================

        if choch == "BULLISH":

            bias = "LONG"

        elif choch == "BEARISH":

            bias = "SHORT"

        elif bos == "BULLISH":

            bias = "LONG"

        elif bos == "BEARISH":

            bias = "SHORT"

        elif trend == "BULLISH":

            bias = "LONG"

        elif trend == "BEARISH":

            bias = "SHORT"

        else:

            bias = "WAIT"

        # =====================================================

        # STRENGTH

        # =====================================================

        strength = 0.0

        if higher_high:

            strength += 25

        if higher_low:

            strength += 25

        if lower_high:

            strength += 25

        if lower_low:

            strength += 25

        if bos != "NONE":

            strength += 15

        if choch != "NONE":

            strength += 10

        strength = min(

            100.0,

            strength,

        )

        # =====================================================

        # REASONS

        # =====================================================

        reasons: list[str] = []

        if higher_high:

            reasons.append(

                "Higher high detected"

            )

        if higher_low:

            reasons.append(

                "Higher low detected"

            )

        if lower_high:

            reasons.append(

                "Lower high detected"

            )

        if lower_low:

            reasons.append(

                "Lower low detected"

            )

        if bos == "BULLISH":

            reasons.append(

                "Bullish break of structure"

            )

        elif bos == "BEARISH":

            reasons.append(

                "Bearish break of structure"

            )

        if choch == "BULLISH":

            reasons.append(

                "Bullish change of character"

            )

        elif choch == "BEARISH":

            reasons.append(

                "Bearish change of character"

            )

        return StructureResult(

            bias=bias,

            strength=strength,

            trend=trend,

            last_high=last_high,

            last_low=last_low,

            previous_high=previous_high,

            previous_low=previous_low,

            higher_high=higher_high,

            higher_low=higher_low,

            lower_high=lower_high,

            lower_low=lower_low,

            bos=bos,

            choch=choch,

            swings=swings,

            events=events,

            reasons=reasons,

        )

