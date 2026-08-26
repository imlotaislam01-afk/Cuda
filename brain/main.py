import asyncio
import os
import time

from brain.execution import ExecutionConfig, ExecutionCoordinator, ExecutionLedger, ExecutionMode, PaperExecutionAdapter
from brain.pipeline import ApexBrainPipeline
from brain.runtime import BrainLoop, DashboardManager, ExecutionConsumer, EngineSupervisor, MarketDataManager, ReconciliationService
from config.runtime import RuntimeConfig
from market.integration.context_adapter import LiveSnapshotContextAdapter
from market.integration.live_snapshot import LiveMarketSnapshot


def build_runtime(runtime: RuntimeConfig):
    snapshot = LiveMarketSnapshot("BTCUSDT")
    ledger = ExecutionLedger(runtime.state_db_path)
    coordinator = ExecutionCoordinator(
        adapter=PaperExecutionAdapter(),
        config=ExecutionConfig(mode=ExecutionMode.PAPER, state_db_path=runtime.state_db_path),
        ledger=ledger,
    )
    pipeline = ApexBrainPipeline()
    market_data = MarketDataManager(snapshot.feed)
    brain_loop = BrainLoop(pipeline)
    execution_consumer = ExecutionConsumer(coordinator)
    reconciliation = ReconciliationService(coordinator)
    dashboard = None
    token = os.environ.get("APEX_DASHBOARD_TOKEN")
    if token:
        from brain.dashboard import create_http_server
        dashboard = DashboardManager(create_http_server(lambda: None, token=token))
    supervisor = EngineSupervisor(
        config=runtime,
        ledger=ledger,
        coordinator=coordinator,
        market_data=market_data,
        brain_loop=brain_loop,
        execution_consumer=execution_consumer,
        reconciliation_service=reconciliation,
        dashboard=dashboard,
    )

    def context_provider():
        return LiveSnapshotContextAdapter(snapshot).build(calculation_time=time.time())

    return supervisor, context_provider


def main() -> None:
    runtime = RuntimeConfig.from_env()
    supervisor, context_provider = build_runtime(runtime)
    started = asyncio.run(supervisor.run_forever(context_provider))

    print()
    print("========================================")
    print("             APEX BRAIN v1")
    print("========================================")
    print(f"Runtime:       {runtime.mode.value}")
    print(f"Lifecycle:     {supervisor.state.value}")
    print(f"Started:       {started}")
    print(f"EXECUTE:       {supervisor.execution_allowed}")
    print("NOTE: Live execution is disabled.")
    print("========================================")
    print()

    supervisor.stop()


if __name__ == "__main__":
    main()
