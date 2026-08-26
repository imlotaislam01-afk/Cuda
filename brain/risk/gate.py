from __future__ import annotations

from dataclasses import dataclass, field
from math import floor, isfinite
from time import time
from typing import Any

from brain.context import ExchangeMetadata


@dataclass(frozen=True)
class RiskConfig:
    account_size: float = 500.0
    risk_per_trade_pct: float = 1.0
    max_leverage: float = 5.0
    max_concurrent_positions: int = 2
    daily_drawdown_kill_pct: float = 3.0
    minimum_confidence: float = 75.0
    fee_rate_pct: float = 0.0
    slippage_pct: float = 0.0
    contract_multiplier: float = 1.0
    quantity_step: float = 0.0
    minimum_quantity: float = 0.0
    maximum_spread_pct: float = 100.0
    max_correlated_positions: int = 1

    @classmethod
    def conservative(cls, **overrides) -> "RiskConfig":
        return cls(**{**{
            "risk_per_trade_pct": 1.0,
            "max_leverage": 5.0,
            "max_concurrent_positions": 2,
            "max_correlated_positions": 1,
            "daily_drawdown_kill_pct": 3.0,
            "minimum_confidence": 75.0,
        }, **overrides})

    @classmethod
    def aggressive(cls, **overrides) -> "RiskConfig":
        return cls(**{**{
            "risk_per_trade_pct": 2.0,
            "max_leverage": 10.0,
            "max_concurrent_positions": 4,
            "max_correlated_positions": 2,
            "daily_drawdown_kill_pct": 6.0,
            "minimum_confidence": 60.0,
        }, **overrides})


@dataclass
class RiskResult:
    approved: bool
    risk_usd: float
    position_size: float
    leverage: float

    reasons: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "risk_usd": self.risk_usd,
            "position_size": self.position_size,
            "leverage": self.leverage,
            "reasons": list(self.reasons),
            "rejection_reasons": list(self.rejection_reasons),
            "metadata": dict(self.metadata),
        }


class RiskGate:

    def __init__(
        self,
        config: RiskConfig | None = None,
        *,
        account_size: float | None = None,
        risk_per_trade_pct: float | None = None,
        max_leverage: float | None = None,
        max_concurrent_positions: int | None = None,
        daily_drawdown_kill_pct: float | None = None,
        min_confidence: float | None = None,
        max_correlated_positions: int | None = None,
        ledger=None,
    ) -> None:

        if config is not None and any(
            value is not None
            for value in (
                account_size,
                risk_per_trade_pct,
                max_leverage,
                max_concurrent_positions,
                daily_drawdown_kill_pct,
                min_confidence,
                max_correlated_positions,
            )
        ):
            raise ValueError("Use config or keyword risk settings, not both")

        self.config = config or RiskConfig(
            account_size=account_size if account_size is not None else 500.0,
            risk_per_trade_pct=risk_per_trade_pct if risk_per_trade_pct is not None else 1.0,
            max_leverage=max_leverage if max_leverage is not None else 5.0,
            max_concurrent_positions=max_concurrent_positions if max_concurrent_positions is not None else 2,
            daily_drawdown_kill_pct=daily_drawdown_kill_pct if daily_drawdown_kill_pct is not None else 3.0,
            minimum_confidence=min_confidence if min_confidence is not None else 75.0,
            max_correlated_positions=max_correlated_positions if max_correlated_positions is not None else 1,
        )
        self._validate_config()

        # Persistent kill switch.
        self._killed = False
        self._audit: list[dict[str, Any]] = []
        self._ledger = ledger
        if ledger is not None and ledger.kill_switch_state == "KILLED":
            self._killed = True

    def _validate_config(self) -> None:
        numeric = (
            self.config.account_size,
            self.config.risk_per_trade_pct,
            self.config.max_leverage,
            self.config.daily_drawdown_kill_pct,
            self.config.minimum_confidence,
            self.config.fee_rate_pct,
            self.config.slippage_pct,
            self.config.contract_multiplier,
            self.config.maximum_spread_pct,
        )
        if not all(isfinite(float(value)) for value in numeric):
            raise ValueError("Risk configuration must be finite")
        if self.config.account_size <= 0 or self.config.risk_per_trade_pct <= 0:
            raise ValueError("Account size and risk percentage must be positive")
        if self.config.max_leverage <= 0 or self.config.contract_multiplier <= 0:
            raise ValueError("Leverage and contract multiplier must be positive")
        if self.config.max_concurrent_positions < 0 or self.config.max_correlated_positions < 0 or self.config.daily_drawdown_kill_pct < 0:
            raise ValueError("Position and drawdown limits cannot be negative")
        if self.config.fee_rate_pct < 0 or self.config.slippage_pct < 0:
            raise ValueError("Fees and slippage cannot be negative")
        if self.config.quantity_step < 0 or self.config.minimum_quantity < 0:
            raise ValueError("Quantity constraints cannot be negative")

    # =========================================================
    # KILL SWITCH
    # =========================================================

    def kill(self, reason: str = "risk policy") -> None:
        """Latch the gate and record the safety transition."""
        self._killed = True
        timestamp = time()
        self._audit.append({"state": "KILLED", "timestamp": timestamp, "reason": reason})
        if self._ledger is not None:
            self._ledger.record_kill_switch("KILLED", reason, event_time=timestamp)

    def reset(self, *, confirm: bool = False, reason: str = "") -> None:
        """Require explicit intent and an audit reason to re-enable trading."""
        if not confirm or not reason.strip():
            raise ValueError("Kill-switch reset requires confirm=True and a reason")
        self._killed = False
        timestamp = time()
        self._audit.append({"state": "RESET", "timestamp": timestamp, "reason": reason})
        if self._ledger is not None:
            self._ledger.record_kill_switch("RESET", reason, event_time=timestamp)

    @property
    def killed(self) -> bool:
        return self._killed

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit)

    # =========================================================
    # INTERNAL EVALUATOR
    # =========================================================

    def _evaluate(
        self,
        *,
        action: str,
        confidence: float,
        entry: float,
        stop_loss: float | None,
        leverage: float,
        open_positions: int,
        correlated_positions: int,
        daily_drawdown_pct: float,
        data_quality: str,
        spread_pct: float | None,
        available_liquidity: float | None,
        exchange_metadata: ExchangeMetadata | None,
        volatility_regime: str | None,
    ) -> RiskResult:

        reasons: list[str] = []
        rejected: list[str] = []

        values = (confidence, entry, leverage, open_positions, correlated_positions, daily_drawdown_pct)
        if not all(isfinite(float(value)) for value in values):
            rejected.append("Risk inputs must be finite")
        if stop_loss is not None and not isfinite(float(stop_loss)):
            rejected.append("Stop-loss must be finite")
        if data_quality not in {"OK", "DATA_VALID"}:
            rejected.append(f"Market data quality is {data_quality}")
        if volatility_regime == "HIGH":
            rejected.append("Volatility regime is too high for the risk policy")
        if spread_pct is not None and (not isfinite(spread_pct) or spread_pct > self.config.maximum_spread_pct):
            rejected.append("Market spread exceeds configured maximum")
        if available_liquidity is not None and (not isfinite(available_liquidity) or available_liquidity <= 0):
            rejected.append("Insufficient market liquidity")

        risk_usd = (
            self.config.account_size
            * self.config.risk_per_trade_pct
            / 100.0
        )

        # -----------------------------------------------------
        # KILL SWITCH
        # -----------------------------------------------------

        if self._killed:
            rejected.append(
                "Risk gate kill switch is active"
            )

        # -----------------------------------------------------
        # ACTION
        # -----------------------------------------------------

        if action not in {"LONG", "SHORT"}:
            rejected.append(
                "Action is not executable"
            )

        # -----------------------------------------------------
        # CONFIDENCE
        # -----------------------------------------------------

        if confidence < self.config.minimum_confidence:
            rejected.append(
                "Confidence below risk threshold"
            )
        else:
            reasons.append(
                "Confidence approved"
            )

        # -----------------------------------------------------
        # ENTRY
        # -----------------------------------------------------

        if entry <= 0:
            rejected.append(
                "Invalid entry price"
            )

        # -----------------------------------------------------
        # STOP LOSS
        # -----------------------------------------------------

        if stop_loss is None:

            rejected.append(
                "Stop-loss is required"
            )

        else:

            if (
                action == "LONG"
                and stop_loss >= entry
            ):
                rejected.append(
                    "LONG stop-loss must be below entry"
                )

            if (
                action == "SHORT"
                and stop_loss <= entry
            ):
                rejected.append(
                    "SHORT stop-loss must be above entry"
                )

            if action in {"LONG", "SHORT"}:
                reasons.append(
                    "Stop-loss geometry approved"
                )

        # -----------------------------------------------------
        # LEVERAGE
        # -----------------------------------------------------

        if leverage <= 0:

            rejected.append(
                "Leverage must be positive"
            )

        elif leverage > self.config.max_leverage:

            rejected.append(
                "Leverage exceeds configured maximum"
            )

        else:

            reasons.append(
                "Leverage approved"
            )

        # -----------------------------------------------------
        # POSITION LIMIT
        # -----------------------------------------------------

        if (
            open_positions
            >= self.config.max_concurrent_positions
        ):

            rejected.append(
                "Position limit reached"
            )

        else:

            reasons.append(
                "Position limit approved"
            )

        if correlated_positions >= self.config.max_correlated_positions:
            rejected.append("Correlated position limit reached")
        else:
            reasons.append("Correlation limit approved")

        # -----------------------------------------------------
        # DAILY DRAWDOWN
        # -----------------------------------------------------

        if (
            daily_drawdown_pct
            >= self.config.daily_drawdown_kill_pct
        ):

            # Latch the kill switch. Once the configured
            # daily drawdown limit is reached, subsequent
            # evaluations remain rejected until reset().
            self.kill()

            rejected.append(
                "Daily drawdown kill switch active"
            )

        else:

            reasons.append(
                "Drawdown approved"
            )

        # -----------------------------------------------------
        # FINAL DECISION
        # -----------------------------------------------------

        approved = len(rejected) == 0

        position_size = 0.0

        if (
            approved
            and stop_loss is not None
            and abs(entry - stop_loss) > 0
        ):

            effective_distance = abs(entry - stop_loss)
            effective_distance += entry * (
                2 * self.config.fee_rate_pct / 100
                + self.config.slippage_pct / 100
            )
            multiplier = exchange_metadata.contract_multiplier if exchange_metadata else self.config.contract_multiplier
            quantity_step = exchange_metadata.quantity_step if exchange_metadata else self.config.quantity_step
            minimum_quantity = exchange_metadata.minimum_quantity if exchange_metadata else self.config.minimum_quantity
            maximum_quantity = exchange_metadata.maximum_quantity if exchange_metadata else None
            position_size = risk_usd / (effective_distance * multiplier)
            if quantity_step > 0:
                position_size = floor(position_size / quantity_step) * quantity_step
                position_size = round(position_size, 12)
            if maximum_quantity is not None and position_size > maximum_quantity:
                position_size = maximum_quantity
            if position_size < minimum_quantity:
                rejected.append("Calculated position size is below minimum quantity")
                position_size = 0.0

        approved = len(rejected) == 0

        return RiskResult(
            approved=approved,
            risk_usd=risk_usd,
            position_size=position_size,
            leverage=leverage,
            reasons=reasons,
            rejection_reasons=rejected,
            metadata={
                "account_size":
                    self.config.account_size,

                "risk_per_trade_pct":
                    self.config.risk_per_trade_pct,

                "max_leverage":
                    self.config.max_leverage,

                "max_concurrent_positions":
                    self.config.max_concurrent_positions,

                "max_correlated_positions":
                    self.config.max_correlated_positions,

                "daily_drawdown_kill_pct":
                    self.config.daily_drawdown_kill_pct,

                "minimum_confidence":
                    self.config.minimum_confidence,

                "killed":
                    self._killed,
            },
        )

    # =========================================================
    # PUBLIC COMPATIBLE API
    # =========================================================

    def evaluate(
        self,
        decision=None,
        *,
        action: str | None = None,
        confidence: float | None = None,
        entry: float | None = None,
        stop_loss: float | None = None,
        leverage: float | None = None,
        open_positions: int | None = None,
        correlated_positions: int = 0,
        daily_drawdown_pct: float = 0.0,

        # Legacy parameter names.
        current_positions: int | None = None,
        requested_leverage: float | None = None,
        data_quality: str = "OK",
        spread_pct: float | None = None,
        available_liquidity: float | None = None,
        exchange_metadata: ExchangeMetadata | None = None,
        volatility_regime: str | None = None,
    ) -> RiskResult:
        """
        Supports both the original APEX API and the newer API.

        Legacy:

            RiskGate().evaluate(
                decision,
                current_positions=0,
                daily_drawdown_pct=0,
                requested_leverage=5,
            )

        New:

            RiskGate().evaluate(
                action="LONG",
                confidence=80,
                entry=100000,
                stop_loss=99500,
                leverage=5,
                open_positions=0,
                daily_drawdown_pct=0,
            )
        """

        # -----------------------------------------------------
        # LEGACY DECISION OBJECT
        # -----------------------------------------------------

        if decision is not None:

            action = getattr(
                decision,
                "action",
                action,
            )

            confidence = getattr(
                decision,
                "confidence",
                confidence,
            )

            entry = getattr(
                decision,
                "entry",
                entry,
            )

            stop_loss = getattr(
                decision,
                "stop_loss",
                stop_loss,
            )

        # -----------------------------------------------------
        # LEGACY POSITION NAME
        # -----------------------------------------------------

        if open_positions is None:

            if current_positions is not None:
                open_positions = current_positions
            else:
                open_positions = 0

        # -----------------------------------------------------
        # LEGACY LEVERAGE NAME
        # -----------------------------------------------------

        if leverage is None:

            if requested_leverage is not None:
                leverage = requested_leverage
            else:
                leverage = self.config.max_leverage

        # -----------------------------------------------------
        # REQUIRED VALUES
        # -----------------------------------------------------

        if action is None:
            action = "WAIT"

        if confidence is None:
            confidence = 0.0

        if entry is None:
            entry = 0.0

        return self._evaluate(
            action=action,
            confidence=float(confidence),
            entry=float(entry),
            stop_loss=stop_loss,
            leverage=float(leverage),
            open_positions=open_positions,
            correlated_positions=correlated_positions,
            daily_drawdown_pct=float(
                daily_drawdown_pct
            ),
            data_quality=data_quality,
            spread_pct=spread_pct,
            available_liquidity=available_liquidity,
            exchange_metadata=exchange_metadata,
            volatility_regime=volatility_regime,
        )
