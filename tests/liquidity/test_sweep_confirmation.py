from market.liquidity import LiquiditySweepDetector


def test_sweep_requires_explicit_reclaim_close():
    detector = LiquiditySweepDetector()

    wick = detector.detect(99, previous_low=100)
    reclaimed = detector.detect(99, previous_low=100, close=101)

    assert wick.confirmed is False
    assert reclaimed.confirmed is True