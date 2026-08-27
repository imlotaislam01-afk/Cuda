import os
import sys

def run_preflight() -> bool:
    print("[PRE-FLIGHT] Verifying Execution Gate Safety...")

    env_mode = os.getenv("APEX_ENV", "").upper()
    if env_mode != "LIVE_PRODUCTION_CONFIRMED":
        print(f"[FAIL] Invalid APEX_ENV: '{env_mode}'.")
        return False

    exchange = os.getenv("APEX_EXCHANGE", "BINANCE").upper()
    if exchange == "BINANCE":
        key = os.getenv("BINANCE_API_KEY", "")
        secret = os.getenv("BINANCE_API_SECRET", "")
    else:
        key = os.getenv("BYBIT_API_KEY", "")
        secret = os.getenv("BYBIT_API_SECRET", "")

    if not key or not secret:
        print(f"[FAIL] Missing {exchange} API credentials.")
        return False

    is_demo = "DEMO_" in key
    mode_str = "DEMO/TESTNET" if is_demo else "LIVE REAL MONEY"
    print(f"[OK] Credentials verified for {exchange} ({mode_str}).")

    db_path = os.getenv("APEX_DB_PATH", "data/ledger.db")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    print("[SUCCESS] All system gates and database paths ready.")
    return True

if __name__ == "__main__":
    if not run_preflight():
        sys.exit(1)
