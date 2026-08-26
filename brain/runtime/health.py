from __future__ import annotations

from dataclasses import dataclass

from .lifecycle import LifecycleState


@dataclass
class RuntimeHealth:
    persistence_ok: bool = True
    exchange_ok: bool = True
    clock_ok: bool = True
    account_ok: bool = True
    reconciliation_ok: bool = True
    protection_ok: bool = True
    market_data_ok: bool = True
    brain_ok: bool = True
    execution_ok: bool = True
    dashboard_ok: bool = True
    lifecycle_state: LifecycleState = LifecycleState.STARTING

    @property
    def execution_ready(self) -> bool:
        return (
            self.persistence_ok
            and self.exchange_ok
            and self.clock_ok
            and self.account_ok
            and self.reconciliation_ok
            and self.protection_ok
            and self.market_data_ok
            and self.brain_ok
            and self.execution_ok
            and self.dashboard_ok
            and self.lifecycle_state is LifecycleState.RUNNING
        )
