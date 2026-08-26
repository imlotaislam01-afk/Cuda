from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class RuntimeMode(str, Enum):
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    LIVE = "LIVE"


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    AGGRESSIVE = "aggressive"


BINANCE_TESTNET_ENDPOINT = "https://testnet.binancefuture.com"
BINANCE_PRODUCTION_ENDPOINT = "https://fapi.binance.com"
BINANCE_TESTNET_API_KEY = "BINANCE_TESTNET_API_KEY"
BINANCE_TESTNET_API_SECRET = "BINANCE_TESTNET_API_SECRET"


@dataclass(frozen=True)
class RuntimeConfig:
    mode: RuntimeMode = RuntimeMode.PAPER
    exchange: str = "PAPER"
    base_url: str | None = None
    risk_profile: RiskProfile = RiskProfile.CONSERVATIVE
    account_size_usd: float = 500.0
    leverage: float = 5.0
    max_position_notional_usd: float = 0.0
    max_drawdown_pct: float = 3.0
    scanner_interval_seconds: int = 15
    state_db_path: str | None = None
    live_enabled: bool = False
    live_confirmation: str | None = None
    api_key: str | None = None
    api_secret: str | None = None

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "RuntimeConfig":
        values = os.environ if environ is None else environ
        raw_mode = values.get("APEX_MODE", "PAPER").strip().upper()
        try:
            mode = RuntimeMode(raw_mode)
        except ValueError as exc:  # pragma: no cover - exercised via tests
            raise ValueError(f"Unsupported runtime mode: {raw_mode!r}") from exc
        exchange = values.get("APEX_EXCHANGE", "PAPER").strip().upper()
        try:
            profile = RiskProfile(values.get("APEX_RISK_PROFILE", "conservative").strip().lower())
        except ValueError as exc:  # pragma: no cover - exercised via tests
            raise ValueError("Unsupported risk profile; expected conservative or aggressive") from exc
        account_size = float(values.get("APEX_ACCOUNT_SIZE_USD", "500"))
        leverage = float(values.get("APEX_LEVERAGE", "5"))
        max_position_notional = float(values.get("APEX_MAX_POSITION_NOTIONAL_USD", "0"))
        max_drawdown_pct = float(values.get("APEX_MAX_DRAWDOWN_PCT", "3"))
        interval = int(values.get("APEX_SCANNER_INTERVAL_SECONDS", "15"))
        state_db_path = values.get("APEX_STATE_DB_PATH")
        live_enabled = _parse_bool(values.get("APEX_LIVE_ENABLED", "false"))
        live_confirmation = values.get("APEX_LIVE_CONFIRMATION")
        base_url = values.get("APEX_BASE_URL")

        if account_size <= 0 or interval <= 0:
            raise ValueError("Account size and scanner interval must be positive")
        if leverage <= 0:
            raise ValueError("Leverage must be positive")
        if max_drawdown_pct < 0:
            raise ValueError("Drawdown limit cannot be negative")
        if max_position_notional < 0:
            raise ValueError("Position notional limit cannot be negative")

        if mode is RuntimeMode.PAPER:
            if exchange != "PAPER":
                raise ValueError("PAPER mode requires exchange=PAPER")
            if base_url:
                raise ValueError("PAPER mode cannot configure an exchange endpoint")
            return cls(mode, exchange, None, profile, account_size, leverage, max_position_notional, max_drawdown_pct,
                       interval, state_db_path, False, None, None, None)

        if exchange != "BINANCE":
            raise ValueError("Only Binance is enabled by this runtime configuration")
        if mode is RuntimeMode.TESTNET:
            if base_url != BINANCE_TESTNET_ENDPOINT:
                raise ValueError("TESTNET requires the official Binance TESTNET endpoint")
            if live_enabled:
                raise ValueError("TESTNET cannot enable LIVE execution")
            return cls(mode, exchange, base_url, profile, account_size, leverage, max_position_notional, max_drawdown_pct,
                       interval, state_db_path, False, None, values.get(BINANCE_TESTNET_API_KEY), values.get(BINANCE_TESTNET_API_SECRET))

        if not live_enabled or live_confirmation != "ENABLE_LIVE_TRADING":
            raise ValueError("LIVE requires explicit enablement and confirmation")
        if base_url != BINANCE_PRODUCTION_ENDPOINT:
            raise ValueError("LIVE requires the explicitly whitelisted Binance production endpoint")
        return cls(mode, exchange, base_url, profile, account_size, leverage, max_position_notional, max_drawdown_pct,
                   interval, state_db_path, True, live_confirmation, values.get("BINANCE_API_KEY"), values.get("BINANCE_API_SECRET"))

    def require_credentials(self) -> None:
        if self.mode is RuntimeMode.PAPER:
            return
        if not self.api_key or not self.api_secret:
            raise ValueError(f"{self.exchange} credentials are required for {self.mode.value}")

    def redacted(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "exchange": self.exchange,
            "base_url": self.base_url,
            "risk_profile": self.risk_profile.value,
            "account_size_usd": self.account_size_usd,
            "leverage": self.leverage,
            "max_position_notional_usd": self.max_position_notional_usd,
            "max_drawdown_pct": self.max_drawdown_pct,
            "scanner_interval_seconds": self.scanner_interval_seconds,
            "state_db_path": self.state_db_path,
            "live_enabled": self.live_enabled,
            "has_api_key": bool(self.api_key),
            "has_api_secret": bool(self.api_secret),
        }


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Boolean configuration values must be true or false")