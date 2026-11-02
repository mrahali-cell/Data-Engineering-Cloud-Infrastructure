"""Airflow task: did the 4 sources load in THIS run, and did tonight's consumption files arrive?

Reads the run log BRONZE.LOAD_RUNS (written by every ingestion job) from the moment this DAG run
started. For each job, its latest line must be SUCCESS (an earlier FAILED line followed by a
successful retry is fine). S2 must have loaded rows: 0 rows means no new file arrived tonight.
Exit code 1 = the task fails = dbt does not run on incomplete data.
"""
import argparse
import os
import sys

sys.path.insert(0, os.environ.get("INGESTION_DIR", "/opt/airflow/ingestion"))
from common import RUN_LOG, connect  # noqa: E402

JOBS = {
    "s1_stock_postgres": "S1 stock",
    "s2_consumption_files": "S2 consumption",
    "s3_bdpm_reference": "S3 drug database",
    "s4_shortages": "S4 shortages",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="start of this DAG run")
    since = ap.parse_args().since

    con = connect()
    cur = con.cursor()
    try:
        cur.execute(f"""
            SELECT job, status, rows_in, rows_loaded, message
            FROM {RUN_LOG}
            WHERE run_at >= TO_TIMESTAMP_TZ(%s)
            QUALIFY ROW_NUMBER() OVER (PARTITION BY job ORDER BY run_at DESC) = 1""", (since,))
        latest = {row[0]: row[1:] for row in cur.fetchall()}
    finally:
        cur.close()
        con.close()

    problems = []
    print(f"Runs logged since {since}:")
    for job, name in JOBS.items():
        if job not in latest:
            print(f"  {name:<18} no run logged")
            problems.append(f"{name}: did not run")
            continue
        status, rows_in, rows_loaded, message = latest[job]
        print(f"  {name:<18} {status:<8} {rows_in} rows read, {rows_loaded} rows loaded")
        if status != "SUCCESS":
            problems.append(f"{name}: {status} ({message})")
    s2 = latest.get("s2_consumption_files")
    if s2 and s2[0] == "SUCCESS" and not s2[2]:
        problems.append("S2 consumption: 0 rows loaded, tonight's files did not arrive")

    if problems:
        print("\nSTOP: dbt will not run on incomplete data.")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("\nAll 4 sources loaded: dbt can run.")


if __name__ == "__main__":
    main()
