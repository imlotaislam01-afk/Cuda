from dataclasses import dataclass
from typing import Any

from .engine import MarketStructureEngine


@dataclass
class MTFStructureResult:
    bias: str
    aligned: bool

    timeframes: dict[str, dict[str, Any]]

    reasons: list[str]
    htf_bias: str = "WAIT"
    mtf_bias: str = "WAIT"
    ltf_bias: str = "WAIT"
    alignment_score: float = 0.0
    conflict: bool = False
    regime: str = "RANGE"
    confidence: float = 0.0
    stale: bool = False
    stale_timeframes: list[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bias": self.bias,
            "aligned": self.aligned,
            "timeframes": self.timeframes,
            "reasons": self.reasons,
            "htf_bias": self.htf_bias,
            "mtf_bias": self.mtf_bias,
            "ltf_bias": self.ltf_bias,
            "alignment_score": self.alignment_score,
            "conflict": self.conflict,
            "regime": self.regime,
            "confidence": self.confidence,
            "stale": self.stale,
            "stale_timeframes": self.stale_timeframes or [],
        }


class MultiTimeframeStructure:

    def __init__(
        self,
        swing_strength: int = 2,
    ):

        self.engine = MarketStructureEngine(
            swing_strength=swing_strength
        )

    def analyze(
        self,
        candles_by_timeframe: dict[
            str,
            list[dict[str, Any]]
        ],
        as_of: float | None = None,
        timeframe_metadata: dict[str, dict[str, float]] | None = None,
        symbol: str | None = None,
    ) -> MTFStructureResult:

        results: dict[
            str,
            dict[str, Any]
        ] = {}

        hierarchy = {
            "4h": "htf", "1h": "htf",
            "15m": "mtf", "5m": "mtf",
            "1m": "ltf",
        }
        biases = {"htf": [], "mtf": [], "ltf": []}

        reasons: list[str] = []
        stale_timeframes = []
        for timeframe, metadata in (timeframe_metadata or {}).items():
            latest = metadata.get("latest_event_time")
            interval = metadata.get("expected_interval")
            threshold = metadata.get("stale_threshold", interval * 2 if interval else 0)
            if as_of is not None and latest is not None and threshold and as_of - latest > threshold:
                stale_timeframes.append(timeframe)

        for timeframe, candles in (
            candles_by_timeframe.items()
        ):

            result = self.engine.analyze(
                candles,
                as_of=as_of,
                symbol=symbol,
            )

            data = result.to_dict()

            results[
                timeframe
            ] = data

            if result.bias == "LONG":
                biases[hierarchy.get(timeframe.lower(), "mtf")].append("LONG")

            elif result.bias == "SHORT":
                biases[hierarchy.get(timeframe.lower(), "mtf")].append("SHORT")

        def group_bias(values):
            if not values or values.count("LONG") == values.count("SHORT"):
                return "WAIT"
            return "LONG" if values.count("LONG") > values.count("SHORT") else "SHORT"

        htf_bias = group_bias(biases["htf"])
        mtf_bias = group_bias(biases["mtf"])
        ltf_bias = group_bias(biases["ltf"])
        group_values = [htf_bias, mtf_bias, ltf_bias]
        active_biases = [value for value in group_values if value != "WAIT"]
        conflict = len(set(active_biases)) > 1
        weights = {"htf": 3, "mtf": 2, "ltf": 1}
        weighted_total = sum(weights[name] for name, value in (("htf", htf_bias), ("mtf", mtf_bias), ("ltf", ltf_bias)) if value != "WAIT")
        winning = htf_bias if htf_bias != "WAIT" else mtf_bias if mtf_bias != "WAIT" else ltf_bias
        weighted_winning = sum(weights[name] for name, value in (("htf", htf_bias), ("mtf", mtf_bias), ("ltf", ltf_bias)) if value == winning)
        alignment_score = 100.0 * weighted_winning / weighted_total if weighted_total else 0.0

        bias = winning if winning != "WAIT" and not (conflict and htf_bias == "WAIT") else "WAIT"

        active = [
            x for x in results.values()
            if x.get("bias") in {
                "LONG",
                "SHORT",
            }
        ]

        aligned = False

        if active:

            active_biases = {
                x["bias"]
                for x in active
            }

            aligned = len(active_biases) == 1

        if aligned:

            reasons.append(
                f"Multi-timeframe structure aligned {bias}"
            )

        else:

            reasons.append(
                "Multi-timeframe structure not fully aligned"
            )

        if conflict:
            reasons.append("Higher and lower timeframe structure conflict")

        if stale_timeframes:
            bias = "WAIT"
            aligned = False
            reasons.append("Stale timeframe structure is unavailable for confirmation")

        return MTFStructureResult(
            bias=bias,
            aligned=aligned,
            timeframes=results,
            reasons=reasons,
            htf_bias=htf_bias,
            mtf_bias=mtf_bias,
            ltf_bias=ltf_bias,
            alignment_score=round(alignment_score, 2),
            conflict=conflict,
            regime=htf_bias if htf_bias != "WAIT" else "RANGE",
            confidence=round(alignment_score, 2),
            stale=bool(stale_timeframes),
            stale_timeframes=stale_timeframes,
        )
