"""
Updated queries against the v2 schema.
Demonstrates that mktcap_usd is usable and Apple's split-adjusted data is correct.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("stocks.db")


def run_queries(db_path: Path = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    # ── Query 1: Cumulative return per company (updated — more companies, longer history)
    print("=" * 65)
    print("QUERY 1 — Cumulative return per company (full history)")
    print("=" * 65)

    q1 = """
    SELECT
        c.name,
        s.sector_level1,
        s.sector_level2,
        fp.asof                                            AS first_date,
        lp.asof                                            AS last_date,
        ROUND(fp.close_usd, 4)                             AS first_close,
        ROUND(lp.close_usd, 4)                             AS last_close,
        ROUND((lp.close_usd - fp.close_usd)
              / fp.close_usd * 100, 2)                     AS cumulative_return_pct
    FROM companies c
    JOIN sectors s ON s.sector_id = c.sector_id
    JOIN prices fp ON fp.company_id = c.company_id
        AND fp.asof = (SELECT MIN(asof) FROM prices WHERE company_id = c.company_id)
    JOIN prices lp ON lp.company_id = c.company_id
        AND lp.asof = (SELECT MAX(asof) FROM prices WHERE company_id = c.company_id)
    ORDER BY cumulative_return_pct DESC;
    """

    for row in con.execute(q1):
        print(f"\n  Company  : {row['name']}")
        print(f"  Sector   : {row['sector_level1']} / {row['sector_level2']}")
        print(f"  Period   : {row['first_date']}  →  {row['last_date']}")
        print(f"  Close    : ${row['first_close']}  →  ${row['last_close']}")
        print(f"  Return   : {row['cumulative_return_pct']}%")

    # ── Query 2: Average market cap per company (uses new mktcap_usd column)
    print("\n" + "=" * 65)
    print("QUERY 2 — Average and peak market cap per company")
    print("=" * 65)

    q2 = """
    SELECT
        c.name,
        s.sector_level1,
        COUNT(p.price_id)                                  AS trading_days,
        COUNT(p.mktcap_usd)                                AS days_with_mktcap,
        ROUND(AVG(p.mktcap_usd) / 1e9, 2)                 AS avg_mktcap_bn,
        ROUND(MAX(p.mktcap_usd) / 1e9, 2)                 AS peak_mktcap_bn
    FROM companies c
    JOIN sectors  s ON s.sector_id  = c.sector_id
    JOIN prices   p ON p.company_id = c.company_id
    GROUP BY c.company_id
    ORDER BY peak_mktcap_bn DESC;
    """

    print()
    for row in con.execute(q2):
        backfill_note = ""
        if row['days_with_mktcap'] < row['trading_days']:
            missing = row['trading_days'] - row['days_with_mktcap']
            backfill_note = f" ({missing} rows NULL — pre-backfill)"
        print(f"  {row['name']}")
        print(f"    Sector        : {row['sector_level1']}")
        print(f"    Trading days  : {row['trading_days']}{backfill_note}")
        print(f"    Avg mkt cap   : ${row['avg_mktcap_bn']}B")
        print(f"    Peak mkt cap  : ${row['peak_mktcap_bn']}B\n")

    # ── Query 3: Apple split-adjusted price check
    print("=" * 65)
    print("QUERY 3 — Apple price sample (split-adjusted)")
    print("=" * 65)

    q3 = """
    SELECT p.asof, p.close_usd, p.volume, p.mktcap_usd
    FROM prices p
    JOIN companies c ON c.company_id = p.company_id
    WHERE c.name = 'Apple'
    ORDER BY p.asof
    LIMIT 5;
    """
    print()
    print(f"  {'Date':<14} {'Close':>10} {'Volume':>15} {'Mkt Cap':>18}")
    print(f"  {'-'*14} {'-'*10} {'-'*15} {'-'*18}")
    for row in con.execute(q3):
        mktcap = f"${row['mktcap_usd']/1e9:.2f}B" if row['mktcap_usd'] else "NULL"
        print(f"  {row['asof']:<14} ${row['close_usd']:>9.4f} {row['volume']:>15,} {mktcap:>18}")

    con.close()


if __name__ == "__main__":
    run_queries()
