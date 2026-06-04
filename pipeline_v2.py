"""
Stock data ETL pipeline — v2.

Schema changes from v1:
  prices gains mktcap_usd REAL (nullable — backfilled where the source CSV provides it)

New data in v2:
  - Apple added as a new company (split-adjusted historical prices)
  - All companies extended to 2023
  - mktcap_usd populated for all rows

Migration strategy:
  - ALTER TABLE ADD COLUMN is used to add mktcap_usd to prices if it doesn't exist yet.
    SQLite sets existing rows to NULL automatically — correct backfill default.
  - The upsert in prices now includes mktcap_usd, so re-running against the new CSV
    writes the value into previously-NULL rows (backfill propagation).
  - All prior idempotency guarantees are preserved:
      sectors/companies: INSERT OR IGNORE
      prices: ON CONFLICT DO UPDATE (upserts close_usd, volume, AND mktcap_usd)
"""

import csv
import sqlite3
from pathlib import Path

DB_PATH  = Path("stocks.db")
CSV_PATH = Path("stock_data_v2.csv")


# ── Schema (original tables unchanged — migration handled separately) ─────────

DDL = """
CREATE TABLE IF NOT EXISTS sectors (
    sector_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_level1 TEXT NOT NULL,
    sector_level2 TEXT NOT NULL,
    UNIQUE (sector_level1, sector_level2)
);

CREATE TABLE IF NOT EXISTS companies (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    sector_id  INTEGER NOT NULL REFERENCES sectors(sector_id)
);

CREATE TABLE IF NOT EXISTS prices (
    price_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    asof       DATE    NOT NULL,
    close_usd  REAL    NOT NULL,
    volume     INTEGER NOT NULL,
    UNIQUE (company_id, asof)
);
"""


# ── Migration ─────────────────────────────────────────────────────────────────

def migrate(con: sqlite3.Connection) -> None:
    """
    Apply incremental schema changes. Each migration is guarded so it only
    runs if the change hasn't been applied yet — safe to call on every run.
    """
    cur = con.cursor()

    # Check which columns prices already has
    cur.execute("PRAGMA table_info(prices)")
    existing_columns = {row[1] for row in cur.fetchall()}

    if "mktcap_usd" not in existing_columns:
        print("Migration: adding mktcap_usd column to prices...")
        # NULL default is intentional: existing rows don't have this value yet.
        # They'll be backfilled when the new CSV is loaded via the upsert below.
        con.execute("ALTER TABLE prices ADD COLUMN mktcap_usd REAL")
        print("Migration complete.")
    else:
        print("Schema up to date, no migration needed.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_or_create_sector(cur: sqlite3.Cursor, level1: str, level2: str) -> int:
    cur.execute(
        "INSERT OR IGNORE INTO sectors (sector_level1, sector_level2) VALUES (?,?)",
        (level1, level2),
    )
    cur.execute(
        "SELECT sector_id FROM sectors WHERE sector_level1=? AND sector_level2=?",
        (level1, level2),
    )
    return cur.fetchone()[0]


def get_or_create_company(cur: sqlite3.Cursor, name: str, sector_id: int) -> int:
    cur.execute(
        "INSERT OR IGNORE INTO companies (name, sector_id) VALUES (?,?)",
        (name, sector_id),
    )
    cur.execute("SELECT company_id FROM companies WHERE name=?", (name,))
    return cur.fetchone()[0]


def upsert_price(
    cur: sqlite3.Cursor,
    company_id: int,
    asof: str,
    close_usd: float,
    volume: int,
    mktcap_usd: float | None,
) -> None:
    cur.execute(
        """
        INSERT INTO prices (company_id, asof, close_usd, volume, mktcap_usd)
        VALUES (?,?,?,?,?)
        ON CONFLICT(company_id, asof) DO UPDATE SET
            close_usd  = excluded.close_usd,
            volume     = excluded.volume,
            mktcap_usd = excluded.mktcap_usd
        """,
        (company_id, asof, close_usd, volume, mktcap_usd),
    )


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(csv_path: Path = CSV_PATH, db_path: Path = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")

    with con:
        con.executescript(DDL)  # CREATE IF NOT EXISTS — safe on existing DB
        migrate(con)            # ADD COLUMN if needed

    inserted = updated = 0

    with open(csv_path, newline="") as fh, con:
        reader = csv.DictReader(fh)
        cur = con.cursor()

        for row in reader:
            sector_id  = get_or_create_sector(cur, row["sector_level1"].strip(),
                                                   row["sector_level2"].strip())
            company_id = get_or_create_company(cur, row["name"].strip(), sector_id)

            # Parse mktcap — treat empty string as NULL
            raw_mktcap = row.get("mktcap_usd", "").strip()
            mktcap_usd = float(raw_mktcap) if raw_mktcap else None

            cur.execute(
                "SELECT price_id FROM prices WHERE company_id=? AND asof=?",
                (company_id, row["asof"]),
            )
            existing = cur.fetchone()

            upsert_price(cur, company_id, row["asof"],
                         float(row["close_usd"]), int(row["volume"]), mktcap_usd)

            if existing:
                updated += 1
            else:
                inserted += 1

    print(f"Pipeline complete: {inserted} rows inserted, {updated} rows updated/backfilled.")
    print(f"Database: {db_path.resolve()}")


if __name__ == "__main__":
    run()
