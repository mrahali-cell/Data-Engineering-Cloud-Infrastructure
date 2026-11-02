"""Run the whole ingestion for one day, in order, like the orchestrator will.

  python run_all.py --day 1            generate day 1 at the hospitals, then ingest all 4 sources
  python run_all.py --day 2
  python run_all.py --day 3 --incident corrupted
  python run_all.py --skip-generate    only ingest (files and database already there)
  python run_all.py --dbt              also start the dbt pipeline in Snowflake at the end

Fault tolerance: if one source fails (an API is down...), the others still run, the failure is
logged in BRONZE.LOAD_RUNS, and the script ends with an error code so the orchestrator alerts.
"""
import argparse
import subprocess
import sys

JOBS = [
    ("S1 stock (Postgres, incremental)", ["python", "jobs/ingest_stock_postgres.py"]),
    ("S2 consumption (files, batch COPY)", ["python", "jobs/ingest_consumption_files.py"]),
    ("S3 drug database (BDPM: medicines + composition, weekly download)", ["python", "jobs/ingest_bdpm.py"]),
    ("S4 shortages (BDPM, change detection)", ["python", "jobs/ingest_shortages.py"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=int, default=1)
    ap.add_argument("--incident", default="none")
    ap.add_argument("--skip-generate", action="store_true")
    ap.add_argument("--dbt", action="store_true")
    a = ap.parse_args()

    subprocess.run(["python", "jobs/bootstrap_snowflake.py"], check=True)
    if not a.skip_generate:
        subprocess.run(["python", "generate_sources.py", "--day", str(a.day), "--incident", a.incident], check=True)

    failed = []
    for name, cmd in JOBS:
        print(f"\n=== {name}")
        if subprocess.run(cmd).returncode != 0:
            failed.append(name)

    if a.dbt and not failed:
        subprocess.run(["python", "-c",
                        "from common import connect; c = connect().cursor(); "
                        "c.execute('EXECUTE TASK MEDIRELAIS.PUBLIC.DAILY_PIPELINE'); print('dbt pipeline started')"],
                       check=True)

    print("\n=== Summary")
    print(f"{len(JOBS) - len(failed)}/{len(JOBS)} sources loaded.")
    if failed:
        print("FAILED: " + ", ".join(failed) + "  (details in MEDIRELAIS.BRONZE.LOAD_RUNS)")
        sys.exit(1)


if __name__ == "__main__":
    main()
