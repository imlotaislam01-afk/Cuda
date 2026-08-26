from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApprovalState:
    state: str
    symbol: str | None
    reason: str
    paper_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class DecisionApproval:
    """Explicit user-facing ACCEPT/CANCEL/WAIT state for paper intents."""

    def __init__(self, intent=None):
        self.intent = intent
        self.state = ApprovalState("WAIT", getattr(intent, "symbol", None), "Awaiting user response")

    def accept(self) -> ApprovalState:
        if self.intent is None or not self.intent.paper_only or not self.intent.approved:
            self.state = ApprovalState("CANCEL", getattr(self.intent, "symbol", None), "Paper risk-approved intent required")
        else:
            self.state = ApprovalState("ACCEPT", self.intent.symbol, "Paper intent accepted")
        return self.state

    def cancel(self, reason: str = "User cancelled") -> ApprovalState:
        self.state = ApprovalState("CANCEL", getattr(self.intent, "symbol", None), reason)
        return self.state

    def timeout(self) -> ApprovalState:
        return self.cancel("Approval timeout")
