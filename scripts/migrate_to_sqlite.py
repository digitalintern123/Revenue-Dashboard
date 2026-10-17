"""
scripts/migrate_to_sqlite.py — one-off copy of every table from the current
Postgres database (Neon) into a SQLite file, then a row-count and totals check.

Run it where both are reachable — on Render that's the service's Shell tab,
after the persistent disk is attached and while DATABASE_URL still points at
Neon:

    python scripts/migrate_to_sqlite.py

By default the source is $DATABASE_URL and the destination is
$DATA_DIR/revenue_analytics.db (DATA_DIR=/var/data on Render). Options:

    --source URL   Postgres URL to copy from (default: $DATABASE_URL)
    --dest PATH    SQLite file to create      (default: $DATA_DIR/revenue_analytics.db)
    --force        overwrite an existing destination file

Nothing is written to the source database.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, event, func, inspect, select  # noqa: E402

from modules import database  # noqa: E402  (ENGINE = source when DATABASE_URL is Postgres)

# Totals compared after copying: (table, column)
_CHECK_SUMS = [
    ("revenue_master", "revenue"),
    ("revenue_master", "pax"),
    ("airport_traffic", "traffic"),
    ("aop_target", "aop"),
    ("aop_target_daily", "aop"),
    ("encalm_eats_dsr", "net_revenue"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=os.environ.get("DATABASE_URL", ""))
    ap.add_argument("--dest", default=os.path.join(database.sqlite_data_dir(), "revenue_analytics.db"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    source_url = database._normalize_database_url(args.source)
    if not source_url.startswith("postgresql"):
        print("Source must be a Postgres DATABASE_URL (set it, or pass --source).")
        return 2
    dest = os.path.abspath(args.dest)
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not args.force:
        print(f"{dest} already exists. Pass --force to overwrite it.")
        return 2
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(dest + suffix):
            os.remove(dest + suffix)

    src = create_engine(source_url, pool_pre_ping=True)
    dst = create_engine(f"sqlite:///{dest}")

    @event.listens_for(dst, "connect")
    def _pragmas(conn, _rec):
        conn.execute("PRAGMA journal_mode=WAL")

    meta = database.Base.metadata
    meta.create_all(dst)

    src_tables = set(inspect(src).get_table_names())
    extra = sorted(src_tables - set(meta.tables))
    if extra:
        print(f"Note: source tables not used by the app (not copied): {', '.join(extra)}")

    ok = True
    for table in meta.sorted_tables:
        if table.name not in src_tables:
            print(f"  {table.name:22} not in source — created empty")
            continue
        cols = [c for c in table.columns if c.name in
                {c2["name"] for c2 in inspect(src).get_columns(table.name)}]
        copied = 0
        with src.connect() as s_conn, dst.begin() as d_conn:
            result = s_conn.execution_options(stream_results=True).execute(select(*cols))
            while True:
                rows = result.mappings().fetchmany(5000)
                if not rows:
                    break
                d_conn.execute(table.insert(), [dict(r) for r in rows])
                copied += len(rows)
        with src.connect() as s_conn, dst.connect() as d_conn:
            n_src = s_conn.execute(select(func.count()).select_from(table)).scalar()
            n_dst = d_conn.execute(select(func.count()).select_from(table)).scalar()
        flag = "OK " if n_src == n_dst else "MISMATCH"
        ok &= n_src == n_dst
        print(f"  {flag} {table.name:22} rows source={n_src:>8,}  sqlite={n_dst:>8,}")

    print("Totals:")
    for tname, col in _CHECK_SUMS:
        if tname not in meta.tables or tname not in src_tables:
            continue
        t = meta.tables[tname]
        with src.connect() as s_conn, dst.connect() as d_conn:
            a = s_conn.execute(select(func.coalesce(func.sum(t.c[col]), 0))).scalar() or 0
            b = d_conn.execute(select(func.coalesce(func.sum(t.c[col]), 0))).scalar() or 0
        same = abs(float(a) - float(b)) < 0.01
        ok &= same
        print(f"  {'OK ' if same else 'MISMATCH'} {tname}.{col}: source={float(a):,.2f}  sqlite={float(b):,.2f}")

    print(f"\nSQLite file: {dest}")
    if ok:
        print("All tables and totals match. Next: remove DATABASE_URL on Render and redeploy.")
        return 0
    print("Some checks did NOT match — keep using Postgres and send this output for review.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
