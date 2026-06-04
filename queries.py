"""
Example queries against the normalized stock schema.

Query 1 – Cumulative return per company over the full period
  Joins companies → prices, uses MIN/MAX aggregation, computes
  (last_close - first_close) / first_close as the total return.

Query 2 – Average daily volume per sector
  Joins sectors → companies → prices, groups by sector.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("stocks.db")


def run_queries(db_path: Path = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    # ── Query 1: Cumulative return per company ────────────────────────────────
    print("=" * 60)
    print("QUERY 1 — Cumulative return per company")
    print("=" * 60)

    q1 = """
    SELECT
        c.name,
        s.sector_level1,
        s.sector_level2,
        MIN(p.asof)                                   AS first_date,
        MAX(p.asof)                                   AS last_date,
        ROUND(first_prices.close_usd, 4)              AS first_close,
        ROUND(last_prices.close_usd,  4)              AS last_close,
        ROUND(
            (last_prices.close_usd - first_prices.close_usd)
            / first_prices.close_usd * 100,
        2)                                            AS cumulative_return_pct
    FROM companies   c
    JOIN sectors     s  ON s.sector_id  = c.sector_id
    JOIN prices      p  ON p.company_id = c.company_id
    -- sub-select to get the price on each company's earliest date
    JOIN prices first_prices
        ON  first_prices.company_id = c.company_id
        AND first_prices.asof = (
            SELECT MIN(asof) FROM prices WHERE company_id = c.company_id
        )
    -- sub-select to get the price on each company's latest date
    JOIN prices last_prices
        ON  last_prices.company_id = c.company_id
        AND last_prices.asof = (
            SELECT MAX(asof) FROM prices WHERE company_id = c.company_id
        )
    GROUP BY c.company_id
    ORDER BY cumulative_return_pct DESC;
    """

    for row in con.execute(q1):
        print(f"\n  Company  : {row['name']}")
        print(f"  Sector   : {row['sector_level1']} / {row['sector_level2']}")
        print(f"  Period   : {row['first_date']}  →  {row['last_date']}")
        print(f"  Close    : ${row['first_close']}  →  ${row['last_close']}")
        print(f"  Return   : {row['cumulative_return_pct']}%")

    # ── Query 2: Average daily volume per sector ──────────────────────────────
    print("\n" + "=" * 60)
    print("QUERY 2 — Average daily volume per sector")
    print("=" * 60)

    q2 = """
    SELECT
        s.sector_level1,
        s.sector_level2,
        COUNT(DISTINCT c.company_id)          AS num_companies,
        ROUND(AVG(p.volume))                  AS avg_daily_volume
    FROM sectors  s
    JOIN companies c ON c.sector_id  = s.sector_id
    JOIN prices    p ON p.company_id = c.company_id
    GROUP BY s.sector_id
    ORDER BY avg_daily_volume DESC;
    """

    print()
    for row in con.execute(q2):
        print(f"  {row['sector_level1']} / {row['sector_level2']}")
        print(f"    Companies       : {row['num_companies']}")
        print(f"    Avg daily volume: {row['avg_daily_volume']:,.0f}\n")

    con.close()


if __name__ == "__main__":
    run_queries()
