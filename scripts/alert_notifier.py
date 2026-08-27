import os
import sys
import json
import urllib.request

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_alert(message: str, level: str = "INFO"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        # Fallback to stdout if alerts are not configured
        print(f"[{level}] {message}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 [APEX {level}] 🚨\n\n{message}",
        "parse_mode": "Markdown"
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as err:
        print(f"[ALERT ERROR] Failed to send Telegram alert: {err}", file=sys.stderr)

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Test alert from APEX trading system."
    send_alert(msg)
