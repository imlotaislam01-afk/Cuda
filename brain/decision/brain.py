from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class DecisionLevels:
    entry: float | None = None
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None


@dataclass
class BrainDecision:
    action: str
    confidence: float
    levels: DecisionLevels
    reasons: list[str] = field(default_factory=list)
    invalidation: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def direction(self) -> str:
        return self.action

    @property
    def entry(self) -> float | None:
        return self.levels.entry

    @property
    def stop_loss(self) -> float | None:
        return self.levels.stop_loss

    @property
    def risk_reward(self) -> float | None:
        if self.levels.entry is None or self.levels.stop_loss is None or self.levels.tp1 is None:
            return None
        risk = abs(self.levels.entry - self.levels.stop_loss)
        return abs(self.levels.tp1 - self.levels.entry) / risk if risk else None

    @property
    def setup_type(self) -> str | None:
        return self.metadata.get("setup_type")

    @property
    def confluence_score(self) -> float:
        return float(self.metadata.get("confluence_score", self.confidence))

    @property
    def event_time(self) -> float | None:
        return self.metadata.get("event_time")

    @property
    def data_quality(self) -> str:
        return self.metadata.get("data_quality", "OK")

    @property
    def reasoning(self) -> list[str]:
        return self.reasons

    @property
    def blocking_conditions(self) -> list[str]:
        return self.invalidation

    @property
    def is_trade(self) -> bool:
        return self.action in {"LONG", "SHORT"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "levels": {
                "entry": self.levels.entry,
                "stop_loss": self.levels.stop_loss,
                "tp1": self.levels.tp1,
                "tp2": self.levels.tp2,
                "tp3": self.levels.tp3,
            },
            "reasons": list(self.reasons),
            "invalidation": list(self.invalidation),
            "direction": self.direction,
            "risk_reward": self.risk_reward,
            "setup_type": self.setup_type,
            "confluence_score": self.confluence_score,
            "event_time": self.event_time,
            "data_quality": self.data_quality,
            "reasoning": list(self.reasoning),
            "blocking_conditions": list(self.blocking_conditions),
            "metadata": dict(self.metadata),
        }


class APEXDecisionBrain:
    """
    Deterministic decision layer.

    It does not place orders.
    It converts already-computed market evidence
    into LONG / SHORT / WAIT.
    """

    def __init__(
        self,
        minimum_confidence: float = 60.0,
    ) -> None:
        self.minimum_confidence = minimum_confidence

    def analyze(
        self,
        context: Any,
    ) -> BrainDecision:

        quality = getattr(context, "data_quality", "OK")
        quality_status = getattr(quality, "status", quality)
        if quality_status not in {"OK", "DATA_VALID"}:
            return BrainDecision(
                action="WAIT",
                confidence=0.0,
                levels=DecisionLevels(),
                reasons=[f"Market data quality is {quality_status}"],
                invalidation=["Valid, complete, non-stale market data required"],
                metadata={"data_quality": quality_status},
            )

        bias = str(
            getattr(context, "bias", "WAIT")
        ).upper()

        score = float(
            getattr(context, "score", 0.0)
        )

        price = float(
            getattr(
                context,
                "current_price",
                0.0,
            )
        )

        if not isfinite(score) or not isfinite(price) or price <= 0:
            return BrainDecision(
                action="WAIT",
                confidence=0.0,
                levels=DecisionLevels(),
                reasons=["Market context contains invalid numeric data"],
                invalidation=["Finite positive price and score required"],
            )

        if hasattr(context, "structure") and getattr(context, "structure") is None:
            return BrainDecision(
                action="WAIT",
                confidence=0.0,
                levels=DecisionLevels(),
                reasons=["Required market structure is unavailable"],
                invalidation=["Structure is required for a live decision"],
                metadata={"data_quality": quality_status},
            )

        mtf = getattr(context, "mtf", None)
        if getattr(mtf, "conflict", False):
            return BrainDecision(
                action="WAIT",
                confidence=0.0,
                levels=DecisionLevels(),
                reasons=["Multi-timeframe structure is conflicting"],
                invalidation=["HTF/MTF/LTF alignment required"],
                metadata={"data_quality": quality_status},
            )
        if getattr(mtf, "stale", False):
            return BrainDecision(
                action="WAIT",
                confidence=0.0,
                levels=DecisionLevels(),
                reasons=["Required timeframe data is stale"],
                invalidation=list(getattr(mtf, "stale_timeframes", [])),
                metadata={"data_quality": quality_status},
            )

        market_regime = str(getattr(context, "market_regime", "")).upper()
        if market_regime in {"BALANCED", "CHOP", "UNKNOWN"}:
            return BrainDecision(
                action="WAIT",
                confidence=0.0,
                levels=DecisionLevels(),
                reasons=[f"Market regime is {market_regime}"],
                invalidation=["Directional regime required"],
                metadata={"data_quality": quality_status},
            )

        if bias not in {"LONG", "SHORT"}:
            return BrainDecision(
                action="WAIT",
                confidence=min(score, 100.0),
                levels=DecisionLevels(),
                reasons=[
                    "Market bias is not directional"
                ],
                invalidation=[
                    "Directional confluence required"
                ],
                metadata={"data_quality": quality_status},
            )

        if score < self.minimum_confidence:
            return BrainDecision(
                action="WAIT",
                confidence=score,
                levels=DecisionLevels(),
                reasons=[
                    f"Confluence score {score:.1f} "
                    f"is below required "
                    f"{self.minimum_confidence:.1f}"
                ],
                invalidation=[
                    "Confidence threshold not met"
                ],
                metadata={"data_quality": quality_status},
            )

        reasons = [
            f"Confluence bias: {bias}",
            f"Confluence score: {score:.1f}",
        ]

        if bias == "LONG":
            action = "LONG"
        else:
            action = "SHORT"

        price_context = getattr(context, "price", None)
        distance = float(getattr(price_context, "atr", None) or getattr(context, "volatility", None) or price * 0.005)
        if not isfinite(distance) or distance <= 0:
            return BrainDecision(
                action="WAIT",
                confidence=score,
                levels=DecisionLevels(),
                reasons=["Stop distance is unavailable or invalid"],
                invalidation=["Valid volatility or ATR is required"],
                metadata={"data_quality": quality_status},
            )
        if bias == "LONG":
            levels = DecisionLevels(price, price - distance, price + distance * 1.5, price + distance * 2, price + distance * 3)
        else:
            levels = DecisionLevels(price, price + distance, price - distance * 1.5, price - distance * 2, price - distance * 3)

        return BrainDecision(
            action=action,
            confidence=min(score, 100.0),
            levels=levels,
            reasons=reasons,
            invalidation=[
                "Market structure invalidation",
                "Liquidity thesis invalidation",
                "Risk gate rejection",
            ],
            metadata={
                "engine": "APEXDecisionBrain",
                "setup_type": "APEX_CONFLUENCE",
                "confluence_score": score,
                "event_time": getattr(context, "event_time", None),
                "data_quality": quality_status,
            },
        )
