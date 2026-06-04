"""
Stock data ETL pipeline.

Schema (3NF):
  sectors   (sector_id PK, sector_level1, sector_level2)
  companies (company_id PK, name, sector_id FK)
  prices    (price_id PK, company_id FK, asof DATE, close_usd REAL, volume INTEGER)

Idempotency strategy:
  - sectors  / companies: INSERT OR IGNORE — natural-key dedup.
  - prices: INSERT OR REPLACE on (company_id, asof) unique constraint,
    so re-running with updated close/volume values syncs them.
"""

import csv
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path("stocks.db")
CSV_PATH = Path("stock_data.csv")


# ── Schema ────────────────────────────────────────────────────────────────────

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
) -> None:
    cur.execute(
        """
        INSERT INTO prices (company_id, asof, close_usd, volume)
        VALUES (?,?,?,?)
        ON CONFLICT(company_id, asof) DO UPDATE SET
            close_usd = excluded.close_usd,
            volume    = excluded.volume
        """,
        (company_id, asof, close_usd, volume),
    )


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(csv_path: Path = CSV_PATH, db_path: Path = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")

    with con:
        con.executescript(DDL)

    inserted = updated = 0

    with open(csv_path, newline="") as fh, con:
        reader = csv.DictReader(fh)
        cur = con.cursor()

        for row in reader:
            sector_id  = get_or_create_sector(cur, row["sector_level1"].strip(),
                                                   row["sector_level2"].strip())
            company_id = get_or_create_company(cur, row["name"].strip(), sector_id)

            # Track whether this is a new row or an update
            cur.execute(
                "SELECT price_id FROM prices WHERE company_id=? AND asof=?",
                (company_id, row["asof"]),
            )
            existing = cur.fetchone()

            upsert_price(cur, company_id, row["asof"],
                         float(row["close_usd"]), int(row["volume"]))

            if existing:
                updated += 1
            else:
                inserted += 1

    print(f"Pipeline complete: {inserted} rows inserted, {updated} rows updated/unchanged.")
    print(f"Database: {db_path.resolve()}")


if __name__ == "__main__":
    run()
