import os
import sys
import sqlite3

DB_PATH = os.getenv("APEX_DB_PATH", "data/ledger.db")

def emergency_flatten():
    print("=" * 60)
    print("  [EMERGENCY] APEX FAIL-CLOSED PANIC KILL-SWITCH TRIGGERED")
    print("=" * 60)

    # 1. Cancel and fail all active ledger intents
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE execution_intents SET status='FAILED' WHERE status IN ('QUEUED', 'PROCESSING');")
            modified = cursor.rowcount
            conn.commit()
            print(f"[KILL-SWITCH] Aborted and marked {modified} active intent(s) as FAILED in ledger.")
        except Exception as e:
            print(f"[ERROR] Failed to update ledger: {e}")
        finally:
            conn.close()

    # 2. Halt Docker Container Execution
    print("[KILL-SWITCH] Stopping containerized trading engine...")
    os.system("docker compose stop apex-engine")

    print("[SAFE STATE] Engine stopped. No new orders will be submitted.")

if __name__ == "__main__":
    emergency_flatten()
