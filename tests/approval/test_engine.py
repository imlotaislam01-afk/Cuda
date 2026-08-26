from types import SimpleNamespace

from brain.approval import DecisionApproval


def test_accept_requires_approved_paper_intent():
    intent = SimpleNamespace(symbol="BTCUSDT", paper_only=True, approved=True)
    approval = DecisionApproval(intent)
    assert approval.state.state == "WAIT"
    assert approval.accept().state == "ACCEPT"


def test_rejected_intent_cannot_be_accepted_and_timeout_cancels():
    approval = DecisionApproval(SimpleNamespace(symbol="BTCUSDT", paper_only=True, approved=False))
    assert approval.accept().state == "CANCEL"
    assert DecisionApproval().timeout().state == "CANCEL"


def test_cancel_is_explicit_and_paper_only():
    state = DecisionApproval().cancel("invalidated")
    assert state.state == "CANCEL"
    assert state.reason == "invalidated"
    assert state.paper_only is True
