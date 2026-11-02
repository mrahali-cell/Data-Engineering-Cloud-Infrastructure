"""Airflow task: what this run did, in one place (read it in the task's log in the Airflow interface)."""
import argparse
import os
import sys

sys.path.insert(0, os.environ.get("INGESTION_DIR", "/opt/airflow/ingestion"))
from common import DB, RUN_LOG, connect  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    since = ap.parse_args().since

    con = connect()
    cur = con.cursor()
    try:
        cur.execute(f"""SELECT job, status, rows_in, rows_loaded FROM {RUN_LOG}
                        WHERE run_at >= TO_TIMESTAMP_TZ(%s) ORDER BY run_at""", (since,))
        runs = cur.fetchall()
        cur.execute(f"""SELECT
            (SELECT MAX(snapshot_date) FROM {DB}.SILVER.SILVER_STOCK),
            (SELECT COUNT(*) FROM {DB}.SILVER.SILVER_STOCK),
            (SELECT COUNT(*) FROM {DB}.SILVER.SILVER_STOCK_QUARANTINE),
            (SELECT COUNT(*) FROM {DB}.SILVER.SILVER_CONSUMPTION),
            (SELECT COUNT(*) FROM {DB}.SILVER.SILVER_CONSUMPTION_QUARANTINE)""")
        snapshot, stock_ok, stock_q, cons_ok, cons_q = cur.fetchone()
        cur.execute(f"""SELECT priority_rank, product_name, from_hospital_id, to_hospital_id,
                               saveable_value_eur, is_national_shortage
                        FROM {DB}.GOLD.GOLD_TRANSFER_SUGGESTIONS
                        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM {DB}.GOLD.GOLD_TRANSFER_SUGGESTIONS)
                        ORDER BY priority_rank""")
        transfers = cur.fetchall()
    finally:
        cur.close()
        con.close()

    print(f"MédiRelais daily run (started {since})\n")
    print("Ingestion")
    for job, status, rows_in, rows_loaded in runs:
        print(f"  {job:<22} {status:<8} {rows_in} read, {rows_loaded} loaded")
    print(f"\nSilver (snapshot {snapshot})")
    print(f"  stock: {stock_ok} clean batches, {stock_q} in quarantine")
    print(f"  consumption: {cons_ok} clean lines, {cons_q} in quarantine")
    total = sum(float(t[4] or 0) for t in transfers)
    print(f"\nGold: {len(transfers)} transfer suggestions, EUR {total:,.0f} saveable")
    for rank, product, src, dst, value, shortage in transfers:
        flag = "  (shortage in France)" if shortage else ""
        print(f"  {rank}. {product}: {src} -> {dst}, EUR {float(value):,.0f}{flag}")


if __name__ == "__main__":
    main()
