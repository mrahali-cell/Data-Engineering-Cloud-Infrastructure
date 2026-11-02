"""Airflow task: play the hospitals' night (the source side of the pipeline).

Runs ingestion/generate_sources.py for one simulated day: new stock movements in the pharmacy
Postgres database (S1) and tonight's consumption files in landing/consumption/dt=.../ (S2).
--day empty = the next day: one more than the days already delivered (dt= folders).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

INGESTION_DIR = Path(os.environ.get("INGESTION_DIR", "/opt/airflow/ingestion"))
LANDING = Path(os.environ.get("LANDING_DIR", INGESTION_DIR / "landing"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="")
    ap.add_argument("--incident", default="none")
    a = ap.parse_args()

    delivered = sorted(p.name for p in (LANDING / "consumption").glob("dt=*"))
    day = int(a.day) if a.day.strip() else len(delivered) + 1
    print(f"Days already delivered: {len(delivered)} ({', '.join(delivered) or 'none'})")
    print(f"Simulating day {day}, incident: {a.incident}")

    cmd = [sys.executable, "generate_sources.py", "--day", str(day)]
    if a.incident == "corrupted":
        cmd += ["--incident", "corrupted"]
    subprocess.run(cmd, cwd=INGESTION_DIR, check=True)    # check=True: an error here fails the task


if __name__ == "__main__":
    main()
