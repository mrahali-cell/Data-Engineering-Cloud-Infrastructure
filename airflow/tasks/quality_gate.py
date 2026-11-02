"""Airflow task: the quality gate between silver and gold.

Silver never deletes a bad row: it puts it in quarantine with a reason. That protects the results,
but if a large share of TONIGHT's data is rejected, the day itself is broken (a corrupted export,
a hospital system bug) and gold should not be rebuilt from what little is left.
So we measure ONE rate for tonight's delivery: the rows rejected by silver among
  - the consumption lines of the latest dt= delivery (about 300 a night), and
  - the stock batches changed by the latest S1 run (about 60 a night).
They are pooled because the stock part alone is too small: 2 or 3 rows more would move it by 5 points.
Not counted as rejected: duplicates (silver keeps one copy, nothing is lost: incident demo 2 stays
green) and batches whose quantity reached 0 (a batch used up is normal business, not bad data).
A normal night rejects about 5 %; a corrupted night (incident demo 1) about 45 %.
Above MAX_REJECT_RATE (15 %) -> exit 1 -> gold is not refreshed and the dashboard keeps
yesterday's results.
"""
import os
import sys

sys.path.insert(0, os.environ.get("INGESTION_DIR", "/opt/airflow/ingestion"))
from common import BRONZE, DB, connect  # noqa: E402

MAX_RATE = float(os.environ.get("MAX_REJECT_RATE", "0.15"))
NOT_ERRORS = "('duplicate_row', 'zero_quantity')"     # not counted as rejected (see above)
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
                                 f"WHERE CONTAINS(_source, %s) AND reject_reason NOT IN {NOT_ERRORS}", (folder,))

        batch = one(cur, f"SELECT _batch_id FROM {BRONZE}.STOCK_RAW ORDER BY _loaded_at DESC LIMIT 1")
        stock_total = one(cur, f"SELECT COUNT(*) FROM {BRONZE}.STOCK_RAW WHERE _batch_id = %s", (batch,))
        stock_rejected = one(cur, f"SELECT COUNT(*) FROM {SILVER}.SILVER_STOCK_QUARANTINE "
                                  f"WHERE _batch_id = %s AND reject_reason NOT IN {NOT_ERRORS}", (batch,))
    finally:
        cur.close()
        con.close()

    total = cons_total + stock_total
    rejected = cons_rejected + stock_rejected
    print(f"Quality gate: at most {MAX_RATE:.0%} of tonight's rows may be rejected")
    print(f"  consumption, delivery {day}: {cons_rejected} rejected / {cons_total}")
    print(f"  stock, batches changed by run {batch}: {stock_rejected} rejected / {stock_total}")
    problems = []
    if not total:
        problems.append("no rows delivered tonight")
    else:
        rate = rejected / total
        print(f"  tonight in total: {rejected} rejected / {total} = {rate:.1%}")
        if rate > MAX_RATE:
            problems.append(f"{rate:.1%} of tonight's rows rejected (max {MAX_RATE:.0%})")

    if problems:
        print("\nSTOP: gold is NOT refreshed, the dashboard keeps yesterday's results.")
        for p in problems:
            print(f"  - {p}")
        print("The rejected rows and their reasons are in SILVER.SILVER_*_QUARANTINE.")
        sys.exit(1)
    print("\nQuality OK: gold can be refreshed.")


if __name__ == "__main__":
    main()
