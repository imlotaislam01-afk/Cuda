from types import SimpleNamespace

from brain.decision import APEXDecisionBrain


def context(
    bias="LONG",
    score=80,
    price=100000,
):
    return SimpleNamespace(
        bias=bias,
        score=score,
        current_price=price,
    )


def test_long_decision():

    result = APEXDecisionBrain().analyze(
        context()
    )

    assert result.action == "LONG"
    assert result.is_trade is True
    assert result.confidence == 80
    assert result.levels.entry == 100000


def test_short_decision():

    result = APEXDecisionBrain().analyze(
        context(
            bias="SHORT",
            score=75,
        )
    )

    assert result.action == "SHORT"


def test_low_confidence_wait():

    result = APEXDecisionBrain(
        minimum_confidence=60
    ).analyze(
        context(
            bias="LONG",
            score=40,
        )
    )

    assert result.action == "WAIT"
    assert result.is_trade is False


def test_neutral_wait():

    result = APEXDecisionBrain().analyze(
        context(
            bias="WAIT",
            score=90,
        )
    )

    assert result.action == "WAIT"


def test_serialization():

    result = APEXDecisionBrain().analyze(
        context()
    )

    data = result.to_dict()

    assert data["action"] == "LONG"
    assert data["levels"]["entry"] == 100000
    assert isinstance(
        data["reasons"],
        list,
    )
