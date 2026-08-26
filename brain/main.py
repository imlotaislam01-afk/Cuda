from brain.context import build_context
from brain.context.market_state import MarketState
from brain.decision import DecisionEngine
from brain.llm import SafeMockLLMProvider
from brain.memory import BrainMemory
from brain.reasoning import ApexReasoner
from brain.risk import RiskConfig, RiskGate
from config.runtime import RiskProfile, RuntimeConfig


def main() -> None:

    runtime = RuntimeConfig.from_env()
    risk_config = RiskConfig.conservative(account_size=runtime.account_size_usd) if runtime.risk_profile is RiskProfile.CONSERVATIVE else RiskConfig.aggressive(account_size=runtime.account_size_usd)

    # ==========================================
    # SIMULATED MARKET STATE
    # ==========================================

    state = MarketState(
        symbol="BTCUSDT",
        timestamp=1,
        price=100000.0,
        timeframe="1m",
        regime="bullish",

        structure={
            "bias": "bullish",
        },

        liquidity={
            "sweep": "sell_side",
        },

        order_flow={
            "bias": "bullish",
        },

        open_interest={
            "change_pct": 5.2,
        },

        volume={
            "rvol": 3.4,
        },
    )

    # ==========================================
    # MEMORY
    # ==========================================

    memory = BrainMemory(max_events=100)

    memory.add(
        timestamp=state.timestamp,
        event_type="MARKET_STATE",
        symbol=state.symbol,
        data=state.to_dict(),
    )

    # ==========================================
    # CONTEXT
    # ==========================================

    context = build_context(state)

    # ==========================================
    # DETERMINISTIC REASONING
    # ==========================================

    reasoner = ApexReasoner()

    reasoning = reasoner.evaluate(
        context["market"]
    )

    # ==========================================
    # DECISION ENGINE
    # ==========================================

    decision_engine = DecisionEngine(
        min_confidence=75.0,
        default_stop_distance_pct=0.5,
    )

    decision = decision_engine.build(
        context["market"],
        reasoning,
    )

    # ==========================================
    # LLM — ADVISORY ONLY
    # ==========================================

    llm = SafeMockLLMProvider()

    llm_result = llm.analyze(
        context["market"],
        context,
    )

    # ==========================================
    # RISK GATE
    # ==========================================

    risk_gate = RiskGate(config=risk_config)

    risk = risk_gate.evaluate(
        decision=decision,
        current_positions=0,
        daily_drawdown_pct=0.0,
        requested_leverage=5.0,
    )

    # ==========================================
    # AUTHORITATIVE EXECUTION FLAG
    # ==========================================

    decision.execute = risk.approved

    # ==========================================
    # OUTPUT
    # ==========================================

    print()
    print("========================================")
    print("             APEX BRAIN v1")
    print("========================================")

    print(f"Symbol:       {decision.symbol}")
    print(f"Bias:         {reasoning.bias}")
    print(f"Confidence:   {reasoning.confidence:.1f}")
    print(f"Action:       {decision.action}")

    print()

    print(f"Entry:        {decision.entry}")
    print(f"Stop Loss:    {decision.stop_loss}")

    print("Take Profit:")

    for index, target in enumerate(
        decision.take_profit,
        start=1,
    ):
        print(f"  TP{index}:       {target}")

    print()

    print("Reasons:")

    for reason in decision.reasons:
        print(f"  + {reason}")

    print()

    print("LLM:")
    print("  Provider:    SafeMockLLMProvider")
    print(f"  Advisory:    {llm_result['advisory']}")
    print(f"  Bias:        {llm_result['bias']}")

    print()

    print("RISK GATE:")
    print(f"  Approved:    {risk.approved}")

    for reason in risk.reasons:
        print(f"  - {reason}")

    print()

    print(f"EXECUTE:       {decision.execute}")

    print()
    print("NOTE: Live execution is disabled.")
    print("========================================")
    print()


if __name__ == "__main__":
    main()