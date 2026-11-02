"""S1 · Pharmacy stock database (Postgres) -> Snowflake bronze. Method: INCREMENTAL PULL + MERGE.

Why this method: the pharmacy system changes all day; copying the whole database every time
would be slow and expensive. We only pull rows whose updated_at is newer than what Snowflake
already has (the watermark), then MERGE them on the key, so a re-run never creates duplicates.

Tables: pharmacy.hospitals, pharmacy.products, pharmacy.stock_batches
     -> BRONZE.HOSPITALS_RAW, BRONZE.PRODUCTS_RAW, BRONZE.STOCK_RAW
"""
import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BRONZE, run_job  # noqa: E402

TABLES = {
    # source table: (bronze table, key, columns)
    "pharmacy.hospitals": ("HOSPITALS_RAW", "hospital_id",
                           ["hospital_id", "hospital_name", "city", "beds", "latitude", "longitude"]),
    "pharmacy.products": ("PRODUCTS_RAW", "product_id",
                          ["product_id", "product_name", "category", "unit_cost_eur", "is_cold_chain",
                           "is_narcotic", "match_keyword"]),
    "pharmacy.stock_batches": ("STOCK_RAW", "batch_id",
                               ["batch_id", "hospital_id", "product_id", "qty_on_hand", "expiry_date",
                                "is_recalled"]),
}


def pg_connect():
    return psycopg2.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                            dbname=os.environ.get("PGDATABASE", "pharmacy_source"),
                            user=os.environ.get("PGUSER", "source"), password=os.environ.get("PGPASSWORD", "source_pw"))


def body(cur, batch_id):
    total_in = total_loaded = 0
    with pg_connect() as pg, pg.cursor() as pg_cur:
        for source, (target, key, cols) in TABLES.items():
            # 1. Watermark = latest change already in Snowflake
            cur.execute(f"SELECT TO_VARCHAR(MAX(updated_at), 'YYYY-MM-DD\"T\"HH24:MI:SS.FF6TZH:TZM') "
                        f"FROM {BRONZE}.{target}")
            watermark = cur.fetchone()[0] or "1900-01-01T00:00:00+00:00"
            # 2. Extract only what changed since
            pg_cur.execute(
                f"SELECT {', '.join(cols)}, to_char(updated_at AT TIME ZONE 'UTC', "
                f"'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') FROM {source} "
                f"WHERE updated_at > %s::timestamptz ORDER BY updated_at", (watermark,))
            rows = pg_cur.fetchall()
            print(f"  {source}: watermark {watermark} -> {len(rows)} new or changed rows")
            total_in += len(rows)
            if not rows:
                continue
            # 3. Land them in a temporary table, then MERGE on the key (idempotent)
            all_cols = cols + ["updated_at"]
            cur.execute(f"CREATE OR REPLACE TEMPORARY TABLE TMP_BATCH AS "
                        f"SELECT {', '.join(all_cols)} FROM {BRONZE}.{target} WHERE 1 = 0")
            placeholders = ", ".join(["%s"] * len(all_cols))
            cur.executemany(f"INSERT INTO TMP_BATCH ({', '.join(all_cols)}) VALUES ({placeholders})", rows)
            updates = ", ".join(f"t.{c} = s.{c}" for c in all_cols if c != key)
            cur.execute(f"""
                MERGE INTO {BRONZE}.{target} t USING TMP_BATCH s ON t.{key} = s.{key}
                WHEN MATCHED THEN UPDATE SET {updates},
                     t._source = 'postgres:{source}', t._loaded_at = CURRENT_TIMESTAMP(), t._batch_id = %s
                WHEN NOT MATCHED THEN INSERT ({', '.join(all_cols)}, _source, _loaded_at, _batch_id)
                     VALUES ({', '.join('s.' + c for c in all_cols)}, 'postgres:{source}',
                             CURRENT_TIMESTAMP(), %s)""", (batch_id, batch_id))
            inserted, updated = cur.fetchone()
            print(f"    MERGE into {target}: {inserted} inserted, {updated} updated")
            total_loaded += inserted + updated
    return total_in, total_loaded


if __name__ == "__main__":
    run_job("s1_stock_postgres", body)
