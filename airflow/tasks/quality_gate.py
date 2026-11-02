"""Airflow task: the quality gate between silver and gold.

Silver never deletes a bad row: it puts it in quarantine with a reason. That protects the results,
but if a large share of TONIGHT's data is rejected, the day itself is broken (a corrupted export,
a hospital system bug) and gold should not be rebuilt from what little is left.
So, for tonight's delivery only:
  - consumption: lines of the latest dt= delivery rejected by silver
  - stock: batches changed by the latest S1 run rejected by silver
Duplicates are not counted: silver keeps one copy and loses nothing (incident demo 2 stays green).
Above MAX_REJECT_RATE (15 %) -> exit 1 -> gold is not refreshed and the dashboard keeps
yesterday's results.
"""
import os
import sys

sys.path.insert(0, os.environ.get("INGESTION_DIR", "/opt/airflow/ingestion"))
from common import BRONZE, DB, connect  # noqa: E402

MAX_RATE = float(os.environ.get("MAX_REJECT_RATE", "0.15"))
SILVER = f"{DB}.SILVER"


def one(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main():
    con = connect()
    cur = con.cursor()
    try:
        day = one(cur, f"SELECT MAX(REGEXP_SUBSTR(_source_file, 'dt=([0-9-]+)', 1, 1, 'e', 1)) "
                       f"FROM {BRONZE}.CONSUMPTION_RAW")
        folder = f"dt={day}/"
        cons_total = one(cur, f"SELECT COUNT(*) FROM {BRONZE}.CONSUMPTION_RAW "
                              f"WHERE CONTAINS(_source_file, %s)", (folder,))
        cons_rejected = one(cur, f"SELECT COUNT(*) FROM {SILVER}.SILVER_CONSUMPTION_QUARANTINE "
                                 f"WHERE CONTAINS(_source, %s) AND reject_reason <> 'duplicate_row'", (folder,))

        batch = one(cur, f"SELECT _batch_id FROM {BRONZE}.STOCK_RAW ORDER BY _loaded_at DESC LIMIT 1")
        stock_total = one(cur, f"SELECT COUNT(*) FROM {BRONZE}.STOCK_RAW WHERE _batch_id = %s", (batch,))
        stock_rejected = one(cur, f"SELECT COUNT(*) FROM {SILVER}.SILVER_STOCK_QUARANTINE "
                                  f"WHERE _batch_id = %s AND reject_reason <> 'duplicate_row'", (batch,))
    finally:
        cur.close()
        con.close()

    checks = [
        (f"consumption, delivery {day}", cons_rejected, cons_total),
        (f"stock, batches changed by run {batch}", stock_rejected, stock_total),
    ]
    problems = []
    print(f"Quality gate: at most {MAX_RATE:.0%} of tonight's rows may be rejected")
    for name, rejected, total in checks:
        if not total:
            problems.append(f"{name}: no rows to check")
            print(f"  {name}: no rows")
            continue
        rate = rejected / total
        print(f"  {name}: {rejected} rejected / {total} = {rate:.1%}")
        if rate > MAX_RATE:
            problems.append(f"{name}: {rate:.1%} rejected (max {MAX_RATE:.0%})")

    if problems:
        print("\nSTOP: gold is NOT refreshed, the dashboard keeps yesterday's results.")
        for p in problems:
            print(f"  - {p}")
        print("The rejected rows and their reasons are in SILVER.SILVER_*_QUARANTINE.")
        sys.exit(1)
    print("\nQuality OK: gold can be refreshed.")


if __name__ == "__main__":
    main()
