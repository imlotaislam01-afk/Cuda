from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any


@dataclass(frozen=True)
class BacktestResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    expectancy: float
    average_r: float
    profit_factor: float | None
    max_drawdown: float
    sharpe_like: float
    average_hold_time: float | None
    setup_performance: dict[str, dict[str, float]]
    regime_performance: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class BacktestEngine:
    """Calculate paper outcomes from canonical, already replayed trade records."""

    def run_replay(self, replay, pipeline) -> BacktestResult:
        """Backtest decisions produced by the canonical replay/pipeline path."""
        records = []
        for step in replay.run_steps(pipeline):
            result = getattr(step, "pipeline_result", step)
            intent = getattr(result, "intent", None)
            records.append({
                "decision": result.decision,
                "risk_approved": result.risk.approved,
                "quantity": intent.quantity if intent is not None else 0,
                "final_price": result.context.current_price,
                "event_time": result.context.event_time,
                "regime": result.context.market_regime,
            })
        return self.run(records)

    def run(self, records) -> BacktestResult:
        returns = []
        holds = []
        setup = {}
        regime = {}
        for record in records:
            decision = record.get("decision") if isinstance(record, dict) else getattr(record, "decision", None)
            if decision is None or not getattr(decision, "is_trade", False):
                continue
            if isinstance(record, dict) and (record.get("risk_approved") is False or record.get("quantity", 1) <= 0):
                continue
            try:
                entry = float(getattr(decision, "entry"))
                stop = float(getattr(decision, "stop_loss"))
                target = float(getattr(getattr(decision, "levels"), "tp1"))
            except (TypeError, ValueError, AttributeError):
                continue
            risk = abs(entry - stop)
            if risk <= 0 or entry <= 0 or stop <= 0 or target <= 0:
                continue
            direction = decision.action
            if isinstance(record, dict) and record.get("high") is not None and record.get("low") is not None:
                high, low = float(record["high"]), float(record["low"])
                stop_hit = low <= stop if direction == "LONG" else high >= stop
                target_hit = high >= target if direction == "LONG" else low <= target
                if stop_hit and target_hit:
                    outcome = -1.0 if record.get("execution_policy", "stop_first") == "stop_first" else abs(target - entry) / risk
                elif stop_hit:
                    outcome = -1.0
                elif target_hit:
                    outcome = abs(target - entry) / risk
                elif record.get("final_price") is not None:
                    final_price = float(record["final_price"])
                    outcome = (final_price - entry) / risk if direction == "LONG" else (entry - final_price) / risk
                else:
                    continue
            elif record.get("final_price") is not None:
                final_price = float(record["final_price"])
                outcome = (final_price - entry) / risk if direction == "LONG" else (entry - final_price) / risk
            else:
                continue
            outcome = round(outcome, 8)
            returns.append(outcome)
            if isinstance(record, dict) and record.get("hold_time") is not None:
                holds.append(float(record["hold_time"]))
            key = decision.setup_type or "UNKNOWN"
            setup.setdefault(key, []).append(outcome)
            regime_key = record.get("regime", "UNKNOWN") if isinstance(record, dict) else "UNKNOWN"
            regime.setdefault(regime_key, []).append(outcome)
        wins = sum(value > 0 for value in returns)
        losses = sum(value <= 0 for value in returns)
        positives = sum(value for value in returns if value > 0)
        negatives = sum(value for value in returns if value < 0)
        average = sum(returns) / len(returns) if returns else 0.0
        variance = sum((value - average) ** 2 for value in returns) / len(returns) if returns else 0.0
        equity = peak = drawdown = 0.0
        for value in returns:
            equity += value
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)

        def summary(values):
            return {"trades": float(len(values)), "wins": float(sum(value > 0 for value in values)), "average_r": sum(values) / len(values) if values else 0.0}

        return BacktestResult(
            len(returns), wins, losses, wins / len(returns) if returns else 0.0,
            average, average, positives / abs(negatives) if negatives else None,
            drawdown, average / sqrt(variance) if variance else 0.0,
            sum(holds) / len(holds) if holds else None,
            {key: summary(values) for key, values in setup.items()},
            {key: summary(values) for key, values in regime.items()},
        )
