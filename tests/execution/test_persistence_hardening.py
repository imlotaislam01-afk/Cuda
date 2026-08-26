import sqlite3

from brain.execution import ExecutionLedger


def test_sqlite_ledger_uses_durable_write_configuration(tmp_path):
    path = str(tmp_path / "durable.sqlite3")
    ledger = ExecutionLedger(path)
    connection = sqlite3.connect(path)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
    connection.close()
    ledger.close()