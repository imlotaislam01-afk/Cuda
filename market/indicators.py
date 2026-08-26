from __future__ import annotations

from dataclasses import dataclass


def _visible_confirmed(candles, as_of=None):
    by_timestamp = {}
    for candle in candles:
        timestamp = candle.get("event_time", candle.get("timestamp"))
        if timestamp is not None:
            timestamp = float(timestamp)
            if as_of is not None and timestamp > as_of:
                continue
        if candle.get("confirmed", True) is False:
            continue
        if timestamp is None:
            continue
        existing = by_timestamp.get(timestamp)
        if existing is None or candle.get("confirmed", True) >= existing.get("confirmed", True):
            by_timestamp[timestamp] = candle
    return [by_timestamp[timestamp] for timestamp in sorted(by_timestamp)]


@dataclass(frozen=True)
class RVOLResult:
    rvol: float | None
    current_volume: float | None
    baseline_volume: float | None
    lookback: int
    event_time: float | None
    data_quality: str
    sample_count: int = 0
    as_of: float | None = None

    def to_dict(self):
        return {
            "rvol": self.rvol,
            "current_volume": self.current_volume,
            "baseline_volume": self.baseline_volume,
            "lookback": self.lookback,
            "event_time": self.event_time,
            "data_quality": self.data_quality,
            "sample_count": self.sample_count,
            "as_of": self.as_of,
        }


class RVOLCalculator:
    def __init__(self, lookback: int = 20):
        if lookback < 1:
            raise ValueError("RVOL lookback must be positive")
        self.lookback = lookback

    def calculate(self, candles, as_of=None) -> RVOLResult:
        visible = _visible_confirmed(candles, as_of)
        if not visible:
            return RVOLResult(None, None, None, self.lookback, None, "DATA_INCOMPLETE", 0, as_of)
        current = visible[-1]
        try:
            current_volume = float(current["volume"])
        except (KeyError, TypeError, ValueError):
            return RVOLResult(None, None, None, self.lookback, float(current["event_time"]), "DATA_INVALID", 0, as_of)
        if current_volume < 0:
            raise ValueError("Candle volume cannot be negative")
        historical = visible[:-1][-self.lookback:]
        if len(historical) < self.lookback:
            return RVOLResult(None, current_volume, None, self.lookback, float(current["event_time"]), "DATA_INCOMPLETE", len(historical), as_of)
        try:
            baseline = sum(float(candle["volume"]) for candle in historical) / self.lookback
        except (KeyError, TypeError, ValueError):
            return RVOLResult(None, current_volume, None, self.lookback, float(current["event_time"]), "DATA_INVALID", len(historical), as_of)
        if baseline < 0:
            raise ValueError("Candle volume cannot be negative")
        if baseline <= 0:
            return RVOLResult(None, current_volume, baseline, self.lookback, float(current["event_time"]), "DATA_INVALID", len(historical), as_of)
        return RVOLResult(
            current_volume / baseline,
            current_volume,
            baseline,
            self.lookback,
            float(current["event_time"]),
            "DATA_VALID",
            len(historical),
            as_of,
        )


@dataclass(frozen=True)
class VolumeProfileResult:
    poc: float | None
    vah: float | None
    val: float | None
    hvn: float | None
    lvn: float | None
    lookback: int
    event_time: float | None
    data_quality: str
    approximation: str = "OHLCV typical-price bin approximation; not exchange volume-at-price"
    sample_count: int = 0
    bin_count: int = 0
    as_of: float | None = None

    def to_dict(self):
        return {
            "poc": self.poc,
            "vah": self.vah,
            "val": self.val,
            "hvn": self.hvn,
            "lvn": self.lvn,
            "lookback": self.lookback,
            "event_time": self.event_time,
            "data_quality": self.data_quality,
            "approximation": self.approximation,
            "sample_count": self.sample_count,
            "bin_count": self.bin_count,
            "as_of": self.as_of,
        }


class VolumeProfileCalculator:
    """Approximate value area by assigning each candle's volume to typical-price bins."""

    def __init__(self, lookback: int = 50, bin_size: float = 1.0, value_area_pct: float = 0.70):
        if lookback < 1 or bin_size <= 0 or not 0 < value_area_pct <= 1:
            raise ValueError("Invalid volume profile configuration")
        self.lookback = lookback
        self.bin_size = bin_size
        self.value_area_pct = value_area_pct

    def calculate(self, candles, as_of=None) -> VolumeProfileResult:
        visible = _visible_confirmed(candles, as_of)[-self.lookback:]
        if not visible:
            return VolumeProfileResult(None, None, None, None, None, self.lookback, None, "DATA_INCOMPLETE", sample_count=0, as_of=as_of)
        bins = {}
        for candle in visible:
            try:
                volume = float(candle["volume"])
                typical = (float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3
            except (KeyError, TypeError, ValueError):
                return VolumeProfileResult(None, None, None, None, None, self.lookback, float(visible[-1]["event_time"]), "DATA_INVALID", sample_count=len(visible), as_of=as_of)
            if volume < 0:
                raise ValueError("Candle volume cannot be negative")
            price_bin = round((typical // self.bin_size) * self.bin_size, 12)
            bins[price_bin] = bins.get(price_bin, 0.0) + volume
        if not bins or sum(bins.values()) <= 0:
            return VolumeProfileResult(None, None, None, None, None, self.lookback, float(visible[-1]["event_time"]), "DATA_INCOMPLETE", sample_count=len(visible), bin_count=len(bins), as_of=as_of)
        poc = max(sorted(bins), key=lambda price: (bins[price], -price))
        target = sum(bins.values()) * self.value_area_pct
        included = {poc}
        covered = bins[poc]
        while covered < target and (min(included) > min(bins) or max(included) < max(bins)):
            candidates = [price for price in (min(included) - self.bin_size, max(included) + self.bin_size) if price in bins and price not in included]
            if not candidates:
                break
            selected = max(candidates, key=lambda price: (bins[price], -price))
            included.add(selected)
            covered += bins[selected]
        vah = max(included)
        val = min(included)
        hvn = max(sorted(bins), key=lambda price: (bins[price], -price))
        lvn = min(sorted(bins), key=lambda price: (bins[price], price))
        return VolumeProfileResult(poc, vah, val, hvn, lvn, self.lookback, float(visible[-1]["event_time"]), "DATA_VALID", sample_count=len(visible), bin_count=len(bins), as_of=as_of)


class VWAPCalculator:
    @staticmethod
    def calculate(candles, as_of=None):
        total_volume = 0.0
        total_value = 0.0
        for candle in candles:
            timestamp = candle.get("event_time", candle.get("timestamp"))
            if as_of is not None and timestamp is not None and float(timestamp) > as_of:
                continue
            volume = float(candle.get("volume", 0.0))
            if volume < 0:
                raise ValueError("Candle volume cannot be negative")
            if volume == 0:
                continue
            typical = (float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3
            total_volume += volume
            total_value += typical * volume
        return total_value / total_volume if total_volume else None


class ATRCalculator:
    def __init__(self, period: int = 14):
        if period < 1:
            raise ValueError("ATR period must be positive")
        self.period = period

    def calculate(self, candles, as_of=None):
        visible = [
            candle for candle in candles
            if as_of is None
            or candle.get("event_time", candle.get("timestamp")) is None
            or float(candle.get("event_time", candle.get("timestamp"))) <= as_of
        ]
        if len(visible) < self.period + 1:
            return None
        ranges = []
        for previous, current in zip(visible, visible[1:]):
            ranges.append(max(
                float(current["high"]) - float(current["low"]),
                abs(float(current["high"]) - float(previous["close"])),
                abs(float(current["low"]) - float(previous["close"])),
            ))
        return sum(ranges[-self.period:]) / self.period

    @staticmethod
    def classify_regime(atr: float | None, price: float, *, low: float, high: float) -> str:
        if atr is None or price <= 0:
            return "UNKNOWN"
        ratio = atr / price
        if ratio < low:
            return "LOW"
        if ratio >= high:
            return "HIGH"
        return "NORMAL"