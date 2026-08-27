#!/bin/bash
set -e

BACKUP_DIR="data/backups"
DB_FILE="data/ledger.db"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "$BACKUP_DIR"

if [ -f "$DB_FILE" ]; then
    # Enable WAL mode for high-concurrency crash resilience
    sqlite3 "$DB_FILE" "PRAGMA journal_mode=WAL;"
    # Online vacuum backup
    sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/ledger_backup_$TIMESTAMP.db'"
    echo "[BACKUP] Ledger successfully backed up to $BACKUP_DIR/ledger_backup_$TIMESTAMP.db"
    # Keep only the last 14 backups
    ls -dt $BACKUP_DIR/ledger_backup_*.db | tail -n +15 | xargs -r rm --
else
    echo "[BACKUP SKIP] No ledger.db found yet."
fi
