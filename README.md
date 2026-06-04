# owl-sse-data
 Stack: Python + SQLite
 Libaries: sqlite3, pathlib, csv, datetime

# Stock Data Pipeline

A Python ETL pipeline that normalizes a denormalized stock price CSV into a SQLite database, with idempotent loading and incremental schema migration.


## What the pipeline does

The source CSV is a flat, denormalized file where company name and sector classification repeat on every price row. The pipeline extracts three normalized entities from it: sectors, companies, and prices

This eliminates redundancy so that if a company ever changes sector, one row changes instead of thousands.

Both pipelines are safe to re-run any number of times against the same database.

---

## Idempotency strategy

Re-running the pipeline against the same CSV, or an updated one, is safe because every write operation is guarded:

**Reference tables (sectors, companies)** use `INSERT OR IGNORE`. The unique constraint on natural keys means a second run simply does nothing for rows that already exist.

**Fact table (prices)** uses a true upsert. This means if a source CSV corrects a historical price (e.g. a split adjustment), re-running the pipeline syncs the change. New rows are inserted; existing rows are updated in place.

---

## Schema migration approach

When `mktcap_usd` was added to the source in v2, the migration needed to add the column to an already-populated table without data loss. The approach:

1. Check the current column list using `PRAGMA table_info(prices)` before attempting any change.
2. If the column is absent, run `ALTER TABLE prices ADD COLUMN mktcap_usd REAL`.
3. SQLite sets the value to `NULL` on all existing rows automatically.
4. The upsert loop then backfills the value by overwriting `NULL` with the real value for every row that appears in the new CSV.

This migration guard is checked on every pipeline run — it's a no-op if the column already exists, so the pipeline stays safe to run repeatedly regardless of database state.

**Backfill design decision**: `NULL` was chosen as the default for rows that pre-date the new column rather than a computed fallback (e.g. deriving market cap from price × shares outstanding). `NULL` accurately represents "we don't have this value", which is more honest than a potentially incorrect imputation. Any downstream query using `mktcap_usd` should handle `NULL` explicitly.


## What I would change at scale

The current implementation uses SQLite and runs as a single-process Python script. That works well for tens of thousands of rows, but several things would need to change to handle hundreds of millions of rows or concurrent writers.

### Database

**Move to PostgreSQL.** SQLite is a file, not a server — it has no connection pooling, no concurrent write support, and no columnar storage options. PostgreSQL handles all of these and is the natural next step for production use.

### Partitioning

The `prices` table would need to be partitioned by date range — typically by year or month. Without partitioning, a query like "all prices in 2020" does a full table scan even with an index. With range partitioning, the query planner prunes to a single partition immediately. 

### Indexing

The current schema relies on the `UNIQUE (company_id, asof)` constraint index. At scale, compound indexes on the most common query patterns would be needed

### Pipeline architecture

The current pipeline reads the entire CSV into a single transaction. At scale this would be replaced with:

**Batch upserts** — instead of one `execute()` per row, use `executemany()` with batches of 1,000–10,000 rows. This reduces round-trip overhead by orders of magnitude.




