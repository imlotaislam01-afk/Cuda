import sqlite3
import time
import os
import sys

DB_PATH = os.getenv("APEX_DB_PATH", "data/ledger.db")

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def fetch_telemetry():
    if not os.path.exists(DB_PATH):
        print(f"Waiting for ledger database at {DB_PATH}...")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check active execution intents
        cursor.execute("""
            SELECT client_order_id, symbol, status, datetime(created_at, 'unixepoch')
            FROM execution_intents
            ORDER BY created_at DESC
            LIMIT 10;
        """)
        intents = cursor.fetchall()

        clear_screen()
        print("=" * 70)
        print("  APEX REAL-TIME TELEMETRY & LEDGER MONITOR")
        print(f"  Database: {DB_PATH} | System Status: ONLINE")
        print("=" * 70)
        print(f"{'ORDER ID':<36} | {'SYMBOL':<8} | {'STATUS':<10} | {'TIMESTAMP'}")
        print("-" * 70)

        if not intents:
            print("  No intents recorded yet. Engine listening for signals...")
        else:
            for row in intents:
                print(f"{row[0]:<36} | {row[1]:<8} | {row[2]:<10} | {row[3]}")

        print("=" * 70)
        print("Press Ctrl+C to exit monitor (engine continues running).")

    except sqlite3.OperationalError as e:
        print(f"Database read lock or pending schema: {e}")
    finally:
        conn.close()

def main():
    while True:
        fetch_telemetry()
        time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[MONITOR] Stopped.")
        sys.exit(0)
