from types import SimpleNamespace

from brain.scanner import MarketScanner


def context(symbol, volume, score, rvol, setup=False):
    return SimpleNamespace(
        symbol=symbol,
        bias="LONG",
        metadata={"volume_24h": volume},
        confluence=SimpleNamespace(score=score, bias="LONG"),
        rvol=SimpleNamespace(rvol=rvol),
        setup=SimpleNamespace(is_setup=setup, setup_type="BREAKOUT_CONTINUATION" if setup else None),
    )


def test_scanner_filters_illiquid_and_ranks_transparently():
    result = MarketScanner().scan([
        context("ETHUSDT", 6_000_000, 60, 2.0, True),
        context("BTCUSDT", 10_000_000, 70, 1.0),
        context("DOGEUSDT", 4_999_999, 100, 5.0, True),
    ])
    assert [item.symbol for item in result.opportunities] == ["ETHUSDT", "BTCUSDT"]
    assert result.rejected_symbols == ("DOGEUSDT",)
    assert result.opportunities[0].score == 80.0


def test_scanner_output_is_deterministic():
    items = [context("BTCUSDT", 6_000_000, 70, 1.5)]
    assert MarketScanner().scan(items).to_dict() == MarketScanner().scan(items).to_dict()
