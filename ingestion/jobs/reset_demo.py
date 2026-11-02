"""Reset the simulation to day 0, so the demo can be replayed from a clean start.

Use it after a rehearsal that damaged the data (a corrupted day, a day replayed by mistake), and before
recording the video. It empties ONLY what the simulator produces; the real public data stays:

  - the hospitals' Postgres database (schema pharmacy): dropped, recreated by the simulator on day 1
  - the landing files (landing/consumption, landing/issues)
  - in Snowflake: BRONZE.HOSPITALS_RAW, PRODUCTS_RAW, STOCK_RAW, CONSUMPTION_RAW are emptied and the staged
    consumption files removed (TRUNCATE also clears COPY's memory, so the files of day 1 can load again)

Kept: S3 (BDPM files), S4 (shortages and their history), the run log LOAD_RUNS, silver and gold
(rebuilt by the next dbt run), and the Airflow history.

Then replay days 1, 2, 3... with the Airflow DAG (Trigger, day empty: it always takes the next day).

  python jobs/reset_demo.py --yes
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BRONZE, STAGE, connect, log_run, new_batch_id  # noqa: E402

LANDING = Path(os.environ.get("LANDING_DIR", "landing"))
BRONZE_TABLES = ["HOSPITALS_RAW", "PRODUCTS_RAW", "STOCK_RAW", "CONSUMPTION_RAW"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="confirm: really empty the simulated data")
    if not ap.parse_args().yes:
        sys.exit("This empties the simulated hospitals' data. Run again with --yes to confirm.")

    # 1. The hospitals' database
    with psycopg2.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                          dbname=os.environ.get("PGDATABASE", "pharmacy_source"),
                          user=os.environ.get("PGUSER", "source"),
                          password=os.environ.get("PGPASSWORD", "source_pw")) as pg, pg.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS pharmacy CASCADE")
    print("1/3 Hospitals' database emptied (schema pharmacy dropped).")

    # 2. The landing files
    for sub in ("consumption", "issues"):
        shutil.rmtree(LANDING / sub, ignore_errors=True)
    print(f"2/3 Landing files removed ({LANDING}/consumption, {LANDING}/issues).")

    # 3. Snowflake bronze
    con = connect()
    cur = con.cursor()
    try:
        for table in BRONZE_TABLES:
            cur.execute(f"TRUNCATE TABLE {BRONZE}.{table}")
        cur.execute(f"REMOVE @{STAGE}/consumption/")
        log_run(cur, "reset_demo", new_batch_id("reset_demo"), "SUCCESS",
                message="simulation reset: " + ", ".join(BRONZE_TABLES) + " emptied")
    finally:
        cur.close()
        con.close()
    print(f"3/3 Snowflake: {', '.join(BRONZE_TABLES)} emptied, staged consumption files removed.")
    print("\nDone. Next: trigger the Airflow DAG with day empty -> day 1, then again for day 2, day 3...")


if __name__ == "__main__":
    main()
