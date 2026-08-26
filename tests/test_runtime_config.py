import pytest

from config.runtime import BINANCE_TESTNET_ENDPOINT, RuntimeConfig, RuntimeMode


def test_runtime_defaults_fail_closed_to_paper():
    config = RuntimeConfig.from_env({})
    assert config.mode is RuntimeMode.PAPER
    assert config.exchange == "PAPER"
    assert config.live_enabled is False
    assert config.state_db_path is None
    config.require_credentials()
    assert config.redacted()["has_api_secret"] is False


def test_testnet_requires_official_endpoint_and_redacts_credentials():
    config = RuntimeConfig.from_env({
        "APEX_MODE": "testnet",
        "APEX_EXCHANGE": "binance",
        "APEX_BASE_URL": BINANCE_TESTNET_ENDPOINT,
        "BINANCE_TESTNET_API_KEY": "key",
        "BINANCE_TESTNET_API_SECRET": "secret",
    })
    assert config.mode is RuntimeMode.TESTNET
    config.require_credentials()
    redacted = config.redacted()
    assert redacted["has_api_key"] is True
    assert redacted["has_api_secret"] is True
    assert "'key'" not in str(redacted)
    assert "'secret'" not in str(redacted)


def test_testnet_cannot_fall_back_to_production_or_live():
    base = {"APEX_MODE": "TESTNET", "APEX_EXCHANGE": "BINANCE", "APEX_BASE_URL": BINANCE_TESTNET_ENDPOINT}
    with pytest.raises(ValueError):
        RuntimeConfig.from_env({**base, "APEX_BASE_URL": "https://fapi.binance.com"})
    with pytest.raises(ValueError):
        RuntimeConfig.from_env({**base, "APEX_LIVE_ENABLED": "true"})


def test_live_requires_independent_explicit_gate():
    base = {"APEX_MODE": "LIVE", "APEX_EXCHANGE": "BINANCE", "APEX_BASE_URL": "https://fapi.binance.com"}
    with pytest.raises(ValueError):
        RuntimeConfig.from_env(base)
    config = RuntimeConfig.from_env({**base, "APEX_LIVE_ENABLED": "true", "APEX_LIVE_CONFIRMATION": "ENABLE_LIVE_TRADING"})
    assert config.live_enabled is True


def test_invalid_runtime_values_fail_fast():
    with pytest.raises(ValueError):
        RuntimeConfig.from_env({"APEX_ACCOUNT_SIZE_USD": "0"})
    with pytest.raises(ValueError):
        RuntimeConfig.from_env({"APEX_SCANNER_INTERVAL_SECONDS": "0"})


def test_runtime_rejects_unknown_mode_and_invalid_safety_limits():
    with pytest.raises(ValueError):
        RuntimeConfig.from_env({"APEX_MODE": "INVALID"})
    with pytest.raises(ValueError):
        RuntimeConfig.from_env({
            "APEX_MODE": "TESTNET",
            "APEX_EXCHANGE": "BINANCE",
            "APEX_BASE_URL": BINANCE_TESTNET_ENDPOINT,
            "APEX_LEVERAGE": "0",
            "BINANCE_TESTNET_API_KEY": "key",
            "BINANCE_TESTNET_API_SECRET": "secret",
        })
    with pytest.raises(ValueError):
        RuntimeConfig.from_env({
            "APEX_MODE": "TESTNET",
            "APEX_EXCHANGE": "BINANCE",
            "APEX_BASE_URL": BINANCE_TESTNET_ENDPOINT,
            "APEX_MAX_DRAWDOWN_PCT": "-1",
            "BINANCE_TESTNET_API_KEY": "key",
            "BINANCE_TESTNET_API_SECRET": "secret",
        })