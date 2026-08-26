from __future__ import annotations

import json
from dataclasses import dataclass

from market.integration.context_adapter import LiveSnapshotContextAdapter
from market.integration.live_snapshot import LiveMarketSnapshot


@dataclass(frozen=True)
class ReplayEvent:
    event_time: float
    kind: str
    payload: dict


class ReplayHarness:
    """Replay an ordered event stream without consulting wall-clock time."""

    def __init__(self, events, context_factory) -> None:
        self.events = tuple(events)
        self.context_factory = context_factory
        if any(current.event_time < previous.event_time for previous, current in zip(self.events, self.events[1:])):
            raise ValueError("Replay events must be chronological")

    def run(self, pipeline):
        results = []
        seen = []
        for event in self.events:
            seen.append(event)
            context = self.context_factory(tuple(seen), event.event_time)
            results.append(pipeline.run(context))
        return results


@dataclass(frozen=True)
class RawBybitEvent:
    event_time: float
    received_time: float
    message: dict


@dataclass
class RawReplayResult:
    pipeline_result: object

    def to_dict(self):
        result = self.pipeline_result
        return {
            "context": result.context.to_dict(),
            "decision": result.decision.to_dict(),
            "risk": result.risk.to_dict(),
            "intent": result.intent.to_dict() if result.intent else None,
        }


class RawBybitReplayHarness:
    """Replay raw Bybit messages through the production feed parser and pipeline."""

    def __init__(self, events, symbol="BTCUSDT", timeframe_metadata=None):
        self.events = tuple(
            event if isinstance(event, RawBybitEvent) else RawBybitEvent(**event)
            for event in events
        )
        self.symbol = symbol
        self.timeframe_metadata = timeframe_metadata or {}
        self.diagnostics: tuple[dict, ...] = ()

    @staticmethod
    def _fingerprint(event: RawBybitEvent) -> str:
        return json.dumps(event.message, sort_keys=True, separators=(",", ":"), default=str)

    def _events_for_cutoff(self, as_of: float | None = None) -> tuple[RawBybitEvent, ...]:
        """Return a stable event-time view and classify unsafe input explicitly."""
        diagnostics: list[dict] = []
        for index, (previous, current) in enumerate(zip(self.events, self.events[1:]), start=1):
            if current.event_time < previous.event_time and (as_of is None or current.event_time <= as_of):
                diagnostics.append({"index": index, "status": "OUT_OF_ORDER", "event_time": current.event_time})
        ordered = tuple(sorted(enumerate(self.events), key=lambda item: (item[1].event_time, item[1].received_time, item[0])))
        seen: set[str] = set()
        selected: list[RawBybitEvent] = []
        for original_index, event in ordered:
            if as_of is not None and event.event_time > as_of:
                continue
            fingerprint = self._fingerprint(event)
            if fingerprint in seen:
                diagnostics.append({"index": original_index, "status": "DUPLICATE", "event_time": event.event_time})
                continue
            seen.add(fingerprint)
            selected.append(event)
        self.diagnostics = tuple(diagnostics)
        return tuple(selected)

    def run(self, pipeline):
        steps = self.run_steps(pipeline)
        if not steps:
            snapshot = LiveMarketSnapshot(self.symbol)
            for event in self._events_for_cutoff():
                snapshot.feed._process_message(event.message, received_time=event.received_time)
            context = LiveSnapshotContextAdapter(snapshot).build(
                calculation_time=self.events[-1].received_time if self.events else 0.0,
            )
            if context is None:
                raise ValueError("Raw replay produced no price-bearing market context")
            context.metadata["timeframe_metadata"] = self.timeframe_metadata
            context.metadata["replay_diagnostics"] = list(self.diagnostics)
            return RawReplayResult(pipeline.run(context))
        return steps[-1]

    def run_steps(self, pipeline, *, as_of: float | None = None):
        snapshot = LiveMarketSnapshot(self.symbol)
        results = []
        events = self._events_for_cutoff(as_of)
        for event in events:
            snapshot.feed._process_message(
                event.message,
                received_time=event.received_time,
            )
            adapter = LiveSnapshotContextAdapter(snapshot)
            context = adapter.build(
                calculation_time=event.received_time,
                as_of=event.event_time,
            )
            if context is None:
                continue
            context.metadata["timeframe_metadata"] = self.timeframe_metadata
            context.metadata["replay_diagnostics"] = list(self.diagnostics)
            results.append(RawReplayResult(pipeline.run(context)))
        return results