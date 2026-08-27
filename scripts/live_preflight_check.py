import os
import sys

def run_preflight() -> bool:
    print("[PRE-FLIGHT] Verifying Live Production Gate Safety...")

    env_mode = os.getenv("APEX_ENV", "").upper()
    if env_mode != "LIVE_PRODUCTION_CONFIRMED":
        print(f"[FAIL] Invalid APEX_ENV: '{env_mode}'. Must be 'LIVE_PRODUCTION_CONFIRMED'.")
        return False

    exchange = os.getenv("APEX_EXCHANGE", "BINANCE").upper()
    if exchange == "BINANCE":
        key = os.getenv("BINANCE_API_KEY", "")
        secret = os.getenv("BINANCE_API_SECRET", "")
    else:
        key = os.getenv("BYBIT_API_KEY", "")
        secret = os.getenv("BYBIT_API_SECRET", "")

    if not key or not secret or "your_" in key:
        print(f"[FAIL] Missing or placeholder {exchange} credentials.")
        return False

    db_path = os.getenv("APEX_DB_PATH", "data/ledger.db")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    print("[SUCCESS] All live production safety checks verified.")
    return True

if __name__ == "__main__":
    if not run_preflight():
        sys.exit(1)
