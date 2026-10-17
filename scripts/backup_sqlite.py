"""Back up the SQLite database, check the copy, and keep a second copy off the server.

Used by backup_db.ps1 (Windows Task Scheduler, daily). Standard library only,
so it runs without the app's packages or secrets.

    python scripts/backup_sqlite.py --db C:\\encalm\\data\\revenue_analytics.db
        --dest C:\\encalm\\backups [--offsite \\\\nas\\encalm-backups] [--keep 30]
        [--keep-offsite 90]

    python scripts/backup_sqlite.py --verify C:\\encalm\\backups\\<file>.db
        (restore test: opens a backup and prints what it holds)

Each backup is made with SQLite's online backup API (safe while the app is
running), checked with PRAGMA integrity_check and a row count, and only then
copied to --offsite. Exit code 0 = success, 1 = failure (the message says why).
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import shutil
import sqlite3
import sys

PREFIX = "revenue_analytics_"
TABLES = ("revenue_master", "airport_traffic", "aop_target", "aop_target_daily",
          "encalm_eats_dsr", "upload_history")


def make_backup(db_path: str, dest_dir: str, now: dt.datetime | None = None) -> str:
    """Copy `db_path` into `dest_dir` as revenue_analytics_YYYY-MM-DD_HHMM.db."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"database not found: {db_path}")
    os.makedirs(dest_dir, exist_ok=True)
    stamp = (now or dt.datetime.now()).strftime("%Y-%m-%d_%H%M")
    dest = os.path.join(dest_dir, f"{PREFIX}{stamp}.db")
    tmp = dest + ".part"
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        out = sqlite3.connect(tmp)
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    os.replace(tmp, dest)
    return dest


def verify_backup(path: str) -> dict:
    """Open a backup read-only; return integrity result, row counts and the
    latest revenue date. Raises ValueError if the copy is damaged or empty."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"integrity_check failed for {path}: {integrity}")
        present = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in TABLES if t in present}
        if "revenue_master" not in counts:
            raise ValueError(f"{path} has no revenue_master table")
        latest = con.execute("SELECT MAX(date) FROM revenue_master").fetchone()[0]
    finally:
        con.close()
    return {"file": path, "size_mb": round(os.path.getsize(path) / 1_048_576, 2),
            "integrity": integrity, "rows": counts, "latest_revenue_date": latest}


def prune(directory: str, keep: int) -> list[str]:
    """Delete all but the newest `keep` backups in `directory`."""
    files = sorted(glob.glob(os.path.join(directory, f"{PREFIX}*.db")))
    removed = files[:-keep] if keep > 0 else []
    for f in removed:
        os.remove(f)
    return removed


def run(db: str, dest: str, offsite: str | None, keep: int, keep_offsite: int) -> dict:
    path = make_backup(db, dest)
    info = verify_backup(path)
    info["pruned_local"] = len(prune(dest, keep))
    if offsite:
        os.makedirs(offsite, exist_ok=True)
        target = os.path.join(offsite, os.path.basename(path))
        shutil.copy2(path, target + ".part")
        os.replace(target + ".part", target)
        verify_backup(target)
        info["offsite_copy"] = target
        info["pruned_offsite"] = len(prune(offsite, keep_offsite))
    return info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db")
    ap.add_argument("--dest")
    ap.add_argument("--offsite")
    ap.add_argument("--keep", type=int, default=30)
    ap.add_argument("--keep-offsite", type=int, default=90)
    ap.add_argument("--verify", metavar="BACKUP_FILE")
    a = ap.parse_args(argv)
    try:
        if a.verify:
            info = verify_backup(a.verify)
        else:
            if not (a.db and a.dest):
                ap.error("--db and --dest are required (or use --verify)")
            info = run(a.db, a.dest, a.offsite or None, a.keep, a.keep_offsite)
    except Exception as exc:          # reported to the caller, which alerts
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    print("OK " + json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
