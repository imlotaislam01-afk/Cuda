from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEvent:
    timestamp: float
    event_type: str
    symbol: str
    data: dict[str, Any] = field(default_factory=dict)


class BrainMemory:
    """
    Short-term memory for the APEX Brain.

    This first version stores events in memory.
    Persistent storage will be added later.
    """

    def __init__(self, max_events: int = 100):
        self.max_events = max_events
        self.events: list[MemoryEvent] = []

    def add(
        self,
        timestamp: float,
        event_type: str,
        symbol: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        event = MemoryEvent(
            timestamp=timestamp,
            event_type=event_type,
            symbol=symbol,
            data=data or {},
        )

        self.events.append(event)

        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]

    def recent(
        self,
        symbol: str | None = None,
        limit: int = 20,
    ) -> list[MemoryEvent]:

        events = self.events

        if symbol:
            events = [
                event
                for event in events
                if event.symbol == symbol
            ]

        return events[-limit:]

    def clear(self) -> None:
        self.events.clear()

    def size(self) -> int:
        return len(self.events)