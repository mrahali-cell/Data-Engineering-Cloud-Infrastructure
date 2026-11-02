"""Airflow task: run one step of the dbt project inside Snowflake, and fail if a model or a test fails.

Usage: run_dbt.py "build --select silver"
Airflow sends the command to Snowflake (EXECUTE DBT PROJECT) and waits for its answer.
Snowflake answers SUCCESS = TRUE or FALSE, plus dbt's own log (STDOUT), printed in the task log.
FALSE, or an error from Snowflake, ends this script with exit code 1: the task fails, and
everything after it waits.
"""
import os
import sys

sys.path.insert(0, os.environ.get("INGESTION_DIR", "/opt/airflow/ingestion"))
from common import DB, connect  # noqa: E402

PROJECT = f"{DB}.PUBLIC.MEDIRELAIS_DBT"
ROLE = os.environ.get("DBT_ROLE", "MEDIRELAIS_PIPELINE")   # dbt runs as the pipeline role, never ACCOUNTADMIN


def main():
    if len(sys.argv) != 2:
        sys.exit('usage: run_dbt.py "<dbt arguments>"')
    args = sys.argv[1].replace("'", "")
    con = connect()
    cur = con.cursor()
    try:
        cur.execute(f"USE ROLE {ROLE}")
        print(f"EXECUTE DBT PROJECT {PROJECT} ARGS = '{args}'")
        cur.execute(f"EXECUTE DBT PROJECT {PROJECT} ARGS = '{args}'")
        cols = [c[0].upper() for c in cur.description]
        result = dict(zip(cols, cur.fetchone()))
    finally:
        cur.close()
        con.close()

    print(result.get("STDOUT") or "")
    ok = result.get("SUCCESS") in (True, "TRUE", "true", 1)
    if not ok:
        print(f"dbt FAILED: {result.get('EXCEPTION') or 'see the dbt log above'}")
        sys.exit(1)
    print("dbt step succeeded.")


if __name__ == "__main__":
    main()
