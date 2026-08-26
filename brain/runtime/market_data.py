from __future__ import annotations


class MarketDataManager:
    """Lifecycle placeholder for the supervised canonical feed owner."""

    def __init__(self) -> None:
        self.running = False

    def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        return True

    def stop(self) -> bool:
        self.running = False
        return True