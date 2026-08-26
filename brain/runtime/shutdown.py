from __future__ import annotations


class ShutdownManager:
    """Small idempotent shutdown admission gate used by the supervisor."""

    def __init__(self) -> None:
        self.accepting_work = True

    def begin(self) -> bool:
        if not self.accepting_work:
            return False
        self.accepting_work = False
        return True