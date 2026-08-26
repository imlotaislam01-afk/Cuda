from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain.decision import BrainDecision
from brain.risk import RiskResult


@dataclass(frozen=True)
class ExecutionIntent:
    symbol: str
    action: str

    entry: float
    stop_loss: float

    tp1: float | None
    tp2: float | None
    tp3: float | None

    quantity: float
    leverage: float

    risk_usd: float

    approved: bool = False

    paper_only: bool = True

    reasons: list[str] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "quantity": self.quantity,
            "leverage": self.leverage,
            "risk_usd": self.risk_usd,
            "approved": self.approved,
            "paper_only": self.paper_only,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExecutionIntent":
        return cls(
            symbol=str(value["symbol"]),
            action=str(value["action"]),
            entry=float(value["entry"]),
            stop_loss=float(value["stop_loss"]),
            tp1=float(value["tp1"]) if value.get("tp1") is not None else None,
            tp2=float(value["tp2"]) if value.get("tp2") is not None else None,
            tp3=float(value["tp3"]) if value.get("tp3") is not None else None,
            quantity=float(value["quantity"]),
            leverage=float(value["leverage"]),
            risk_usd=float(value["risk_usd"]),
            approved=bool(value["approved"]),
            paper_only=bool(value.get("paper_only", True)),
            reasons=list(value.get("reasons", [])),
            metadata=dict(value.get("metadata", {})),
        )


class ExecutionIntentBuilder:

    def build(
        self,
        *,
        symbol: str,
        decision: BrainDecision,
        risk: RiskResult,
    ) -> ExecutionIntent:

        entry = decision.levels.entry
        stop = decision.levels.stop_loss

        if entry is None:
            raise ValueError(
                "Execution requires entry"
            )

        if stop is None:
            raise ValueError(
                "Execution requires stop-loss"
            )

        approved = (
            decision.is_trade
            and risk.approved
        )

        reasons = list(
            decision.reasons
        )

        reasons.extend(
            risk.reasons
        )

        reasons.extend(
            risk.rejection_reasons
        )

        return ExecutionIntent(
            symbol=symbol,
            action=decision.action,
            entry=entry,
            stop_loss=stop,
            tp1=decision.levels.tp1,
            tp2=decision.levels.tp2,
            tp3=decision.levels.tp3,
            quantity=risk.position_size,
            leverage=risk.leverage,
            risk_usd=risk.risk_usd,
            approved=approved,
            paper_only=True,
            reasons=reasons,
            metadata={
                "execution_mode": "PAPER_ONLY",
                "live_execution": False,
            },
        )
