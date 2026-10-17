"""scripts/backup_sqlite.py: backup, integrity check, off-server copy, pruning."""

import datetime as dt
import importlib.util
import os
import sqlite3

import pytest

_spec = importlib.util.spec_from_file_location(
    "backup_sqlite", os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "backup_sqlite.py"))
bk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bk)


def _db(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE revenue_master (date TEXT, revenue REAL)")
    con.executemany("INSERT INTO revenue_master VALUES (?, ?)",
                    [("2026-09-29", 10.0), ("2026-09-30", 20.0)])
    con.commit()
    con.close()
    return str(path)


def test_backup_verify_and_offsite_copy(tmp_path):
    db = _db(tmp_path / "live.db")
    rc = bk.main(["--db", db, "--dest", str(tmp_path / "local"), "--offsite", str(tmp_path / "off")])
    assert rc == 0
    local = os.listdir(tmp_path / "local")
    assert len(local) == 1 and local == os.listdir(tmp_path / "off")
    info = bk.verify_backup(str(tmp_path / "off" / local[0]))
    assert info["integrity"] == "ok"
    assert info["rows"]["revenue_master"] == 2 and info["latest_revenue_date"] == "2026-09-30"


def test_prune_keeps_newest(tmp_path):
    db = _db(tmp_path / "live.db")
    for h in range(5):
        bk.make_backup(db, str(tmp_path / "b"), now=dt.datetime(2026, 10, 1, h))
    removed = bk.prune(str(tmp_path / "b"), keep=2)
    assert len(removed) == 3
    assert sorted(os.listdir(tmp_path / "b")) == [
        "revenue_analytics_2026-10-01_0300.db", "revenue_analytics_2026-10-01_0400.db"]


def test_damaged_or_missing_database_fails(tmp_path, capsys):
    assert bk.main(["--db", str(tmp_path / "nope.db"), "--dest", str(tmp_path / "b")]) == 1
    assert "FAILED" in capsys.readouterr().out
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database at all" * 100)
    with pytest.raises(Exception):
        bk.verify_backup(str(bad))
