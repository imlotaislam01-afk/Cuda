from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from brain.confluence import ConfluenceEngine
from brain.decision import APEXDecisionBrain, BrainDecision
from brain.execution import ExecutionIntent, ExecutionIntentBuilder
from brain.fvg import FVGEngine, OrderBlockEngine
from brain.intelligence import AbsorptionEngine, AggressionEngine, EffortModel, MicrostructureEngine, RegimeEngine
from brain.liquidity import LiquidityEngine
from brain.oi import OIEngine, OISnapshot
from brain.risk import RiskGate, RiskResult
from brain.structure import MarketStructureEngine, MultiTimeframeStructure
from brain.setup import SetupEngine
from brain.entry import EntryEngine
from brain.monitoring import PreExpansionDetector
from brain.observability import ObservabilityRecorder
from brain.value import ValueMigrationEngine
from market.orderflow import OrderFlowEngine
from market.indicators import ATRCalculator, RVOLCalculator, VolumeProfileCalculator, VWAPCalculator
from config.settings import (
    ATR_PRICE_HIGH_THRESHOLD,
    ATR_PRICE_LOW_THRESHOLD,
    FUNDING_EXTREME_NEGATIVE,
    FUNDING_EXTREME_POSITIVE,
    RVOL_HIGH_THRESHOLD,
)


@dataclass
class PipelineResult:
    context: Any
    decision: BrainDecision
    risk: RiskResult
    intent: ExecutionIntent | None

    def to_dict(self):
        return {
            "context": self.context.to_dict(),
            "decision": self.decision.to_dict(),
            "risk": self.risk.to_dict(),
            "intent": self.intent.to_dict() if self.intent else None,
        }


class ApexBrainPipeline:
    """One deterministic market-context-to-paper-intent execution path."""

    def __init__(self, risk_gate: RiskGate | None = None) -> None:
        self.structure = MarketStructureEngine(swing_strength=1)
        self.mtf = MultiTimeframeStructure(swing_strength=1)
        self.liquidity = LiquidityEngine()
        self.fvg = FVGEngine()
        self.order_blocks = OrderBlockEngine()
        self.orderflow = OrderFlowEngine()
        self.atr = ATRCalculator()
        self.rvol = RVOLCalculator()
        self.volume_profile = VolumeProfileCalculator()
        self.value = ValueMigrationEngine()
        self.aggression = AggressionEngine()
        self.absorption = AbsorptionEngine()
        self.regime = RegimeEngine()
        self.effort = EffortModel(self.aggression, self.absorption)
        self.setup = SetupEngine()
        self.entry = EntryEngine()
        self.pre_expansion = PreExpansionDetector()
        self.observability = ObservabilityRecorder()
        self.oi = OIEngine()
        self.microstructure = MicrostructureEngine()
        self.confluence = ConfluenceEngine()
        self.decision = APEXDecisionBrain()
        self.risk = risk_gate or RiskGate()
        self.intent = ExecutionIntentBuilder()

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return value.to_dict() if hasattr(value, "to_dict") else vars(value)

    def run(
        self,
        context,
        *,
        open_positions: int = 0,
        daily_drawdown_pct: float = 0.0,
    ) -> PipelineResult:
        as_of = context.event_time
        candles = [vars(candle) for candle in context.candles]
        structure = self.structure.analyze(
            candles,
            as_of=as_of,
            symbol=context.symbol,
        )

        timeframe_candles = context.metadata.get("candles_by_timeframe", {})
        if not timeframe_candles and candles:
            timeframe_candles = {context.price.timeframe: candles}
        mtf = self.mtf.analyze(
            timeframe_candles,
            as_of=as_of,
            timeframe_metadata=context.metadata.get("timeframe_metadata"),
            symbol=context.symbol,
        )

        self.liquidity.symbol = context.symbol.upper()
        liquidity = self.liquidity.analyze(candles, as_of=as_of)
        fvg = self.fvg.analyze(candles, as_of=as_of, symbol=context.symbol)
        order_blocks = self.order_blocks.analyze(candles, as_of=as_of, symbol=context.symbol)
        vwap = VWAPCalculator.calculate(candles, as_of=as_of)
        volatility = self.atr.calculate(candles, as_of=as_of)
        volatility_regime = self.atr.classify_regime(
            volatility,
            context.current_price,
            low=ATR_PRICE_LOW_THRESHOLD,
            high=ATR_PRICE_HIGH_THRESHOLD,
        )
        rvol = self.rvol.calculate(candles, as_of=as_of)
        volume_profile = self.volume_profile.calculate(candles, as_of=as_of)
        value = self.value.analyze(candles, as_of=as_of, symbol=context.symbol)
        orderbook_imbalance = context.order_book.imbalance if context.order_book else None
        flow = context.orderflow
        if context.trades:
            flow = self.orderflow.analyze(
                [vars(trade) for trade in context.trades],
                orderbook_imbalance=orderbook_imbalance or 0.0,
                symbol=context.symbol,
            )
        flow_data = self._dict(flow)
        aggression = self.aggression.analyze(candles, flow_data, as_of=as_of, symbol=context.symbol)
        absorption = self.absorption.analyze(candles, flow_data, as_of=as_of, symbol=context.symbol)
        regime = self.regime.analyze(
            candles,
            structure=structure,
            value=value,
            aggression=aggression,
            as_of=as_of,
            symbol=context.symbol,
        )
        effort = self.effort.analyze(
            candles,
            flow_data,
            structure=structure,
            value=value,
            as_of=as_of,
            symbol=context.symbol,
        )
        oi = context.oi
        if oi is None and context.oi_change is not None and context.price.change_pct is not None:
            oi = self.oi.analyze(OISnapshot(
                price_change_pct=context.price.change_pct,
                oi_change_pct=context.oi_change,
                oi_value=context.open_interest,
                volume_ratio=context.price.volume_ratio,
                funding_rate=context.funding,
            ))
        liquidity_data = self._dict(liquidity)
        fvg_data = self._dict(fvg)
        confirmed_sweep = liquidity.latest_sweep is not None and liquidity.latest_sweep.displacement
        micro = self.microstructure.analyze({
            "order_flow": flow_data,
            "orderbook": ({"imbalance": orderbook_imbalance} if orderbook_imbalance is not None else {}),
            "liquidity": {
                "sweep": "sell_side" if confirmed_sweep and liquidity.bias == "LONG" else "buy_side" if confirmed_sweep and liquidity.bias == "SHORT" else "none",
                "sweep_strength": liquidity.confidence / 100.0,
            },
        })

        signals = []
        if structure.bias in {"LONG", "SHORT"}:
            signals.append(self.confluence.structure("BULLISH" if structure.bias == "LONG" else "BEARISH"))
        if liquidity.latest_sweep is not None and liquidity.latest_sweep.displacement and liquidity.bias in {"LONG", "SHORT"}:
            signals.append(self.confluence.liquidity("BULLISH" if liquidity.bias == "LONG" else "BEARISH"))
        if fvg.bias in {"LONG", "SHORT"}:
            signals.append(self.confluence.fvg("BULLISH" if fvg.bias == "LONG" else "BEARISH"))
        if order_blocks.bias in {"LONG", "SHORT"}:
            signals.append(self.confluence.order_block("BULLISH" if order_blocks.bias == "LONG" else "BEARISH"))
        if flow_data.get("bias") in {"bullish", "bearish"}:
            signals.append(self.confluence.orderflow("BULLISH" if flow_data["bias"] == "bullish" else "BEARISH"))
        if oi is not None and oi.direction in {"BULLISH", "BEARISH"} and context.price.change_pct is not None and context.oi_change is not None:
            signals.append(self.confluence.oi(
                oi.direction,
                confidence=oi.confidence,
                price_change_pct=oi.price_change_pct,
                oi_change_pct=oi.oi_change_pct,
                interpretation=oi.regime,
                event_time=context.event_time,
            ))
        if mtf.aligned and not mtf.conflict and mtf.bias in {"LONG", "SHORT"}:
            signals.append(self.confluence.mtf(
                "BULLISH" if mtf.bias == "LONG" else "BEARISH",
                mtf.alignment_score,
                reason=f"{mtf.bias} HTF/MTF/LTF alignment",
            ))
        if micro.bias in {"LONG", "SHORT"}:
            residual_micro = micro.score
            if flow_data.get("bias") in {"bullish", "bearish"}:
                residual_micro -= 20.0
                if flow_data.get("aggression") == "strong":
                    residual_micro -= 10.0
                if flow_data.get("absorption"):
                    residual_micro -= 10.0
            if confirmed_sweep:
                residual_micro -= 25.0
            residual_micro = min(10.0, max(0.0, residual_micro * 0.5))
            if residual_micro > 0:
                signals.append(self.confluence.microstructure(
                    "BULLISH" if micro.bias == "LONG" else "BEARISH",
                    residual_micro,
                    components={"book_bias": micro.book_bias, "cvd": flow_data.get("cumulative_delta")},
                ))
        if vwap is not None:
            vwap_tolerance = max(abs(vwap) * 0.0001, 1e-12)
            if abs(context.current_price - vwap) <= vwap_tolerance:
                pass
            elif context.current_price > vwap:
                signals.append(self.confluence.vwap("BULLISH", "Price above VWAP"))
            elif context.current_price < vwap:
                signals.append(self.confluence.vwap("BEARISH", "Price below VWAP"))
        if context.funding is not None:
            if context.funding >= FUNDING_EXTREME_POSITIVE:
                signals.append(self.confluence.funding("BEARISH", "Extreme positive funding; contrarian bearish context"))
            elif context.funding <= FUNDING_EXTREME_NEGATIVE:
                signals.append(self.confluence.funding("BULLISH", "Extreme negative funding; contrarian bullish context"))
        directional = next((signal.direction for signal in signals if signal.direction in {"BULLISH", "BEARISH"}), None)
        if directional and rvol.rvol is not None and rvol.rvol >= RVOL_HIGH_THRESHOLD:
            signals.append(self.confluence.rvol(directional, f"RVOL confirmation {rvol.rvol:.2f}x"))
        if volume_profile.poc is not None:
            if context.current_price > volume_profile.vah:
                signals.append(self.confluence.volume_profile("BULLISH", "Price above value area high"))
            elif context.current_price < volume_profile.val:
                signals.append(self.confluence.volume_profile("BEARISH", "Price below value area low"))
        if value.state == "DIRECTIONAL_AUCTION":
            if value.migration == "HIGHER" and value.acceptance == "HIGHER":
                signals.append(self.confluence.value("BULLISH", "Value migrating higher with acceptance"))
            elif value.migration == "LOWER" and value.acceptance == "LOWER":
                signals.append(self.confluence.value("BEARISH", "Value migrating lower with acceptance"))
        confluence = self.confluence.analyze(signals)
        enriched = replace(
            context,
            structure=structure,
            mtf=mtf,
            liquidity=liquidity,
            fvg=fvg,
            order_blocks=order_blocks,
            orderflow=flow,
            microstructure=micro,
            confluence=confluence,
            oi=oi,
            vwap=vwap,
            volatility=volatility,
            volatility_regime=volatility_regime,
            rvol=rvol,
            volume_profile=volume_profile,
            value=value,
            aggression=aggression,
            absorption=absorption,
            market_regime=regime.state,
            effort=effort,
        )
        setup = self.setup.analyze(enriched)
        entry = self.entry.analyze(setup)
        enriched = replace(enriched, setup=setup, entry=entry)
        pre_expansion = self.pre_expansion.analyze(enriched, as_of=as_of)
        enriched = replace(enriched, pre_expansion=pre_expansion)
        decision = self.decision.analyze(enriched)
        risk = self.risk.evaluate(
            decision=decision,
            open_positions=open_positions,
            daily_drawdown_pct=daily_drawdown_pct,
            data_quality=enriched.data_quality.status,
            volatility_regime=enriched.volatility_regime,
            exchange_metadata=enriched.exchange_metadata,
        )
        if decision.is_trade and not risk.approved:
            decision = BrainDecision(
                action="WAIT",
                confidence=decision.confidence,
                levels=decision.levels,
                reasons=["Risk gate rejected the setup"],
                invalidation=list(risk.rejection_reasons),
                metadata={
                    "event_time": enriched.event_time,
                    "data_quality": enriched.data_quality.status,
                    "confluence_score": decision.confluence_score,
                },
            )
        intent = None
        if decision.is_trade and risk.approved and decision.entry is not None and decision.stop_loss is not None:
            intent = self.intent.build(symbol=enriched.symbol, decision=decision, risk=risk)
        final_result = PipelineResult(enriched, decision, risk, intent)
        return PipelineResult(replace(enriched, observability=self.observability.record(final_result)), decision, risk, intent)


BrainPipeline = ApexBrainPipeline