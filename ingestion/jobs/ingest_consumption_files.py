"""S2 · Daily consumption files -> Snowflake bronze. Method: BATCH FILE LOAD (stage + COPY INTO).

Why this method: consumption is reported once a night per hospital as a file; the decision
(what to order, what to transfer) is daily, so batch is enough and cheap to replay.

  landing/consumption/dt=YYYY-MM-DD/H01.csv ... H12.csv
    -> uploaded to Snowflake's internal stage RAW_STAGE
    -> COPY INTO BRONZE.CONSUMPTION_RAW, columns matched BY NAME (a renamed column lands in its
       own column instead of breaking the load: schema drift stays visible)

Re-running is safe: COPY remembers which files it already loaded (load metadata) and skips them.
--force reloads everything anyway: that simulates an operator mistake for incident demo #2.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BRONZE, STAGE, run_job  # noqa: E402

LANDING = Path(os.environ.get("LANDING_DIR", "landing")) / "consumption"


def upload_to_internal_stage(cur, files):
    for f in files:
        cur.execute(f"PUT 'file://{f.resolve()}' @{STAGE}/consumption/{f.parent.name}/ "
                    "AUTO_COMPRESS = FALSE OVERWRITE = FALSE")
    return f"@{STAGE}/consumption/"


def make_body(force):
    def body(cur, batch_id):
        files = sorted(LANDING.glob("dt=*/*.csv"))
        if not files:
            raise FileNotFoundError(f"no files in {LANDING}: run generate_sources.py first")
        lines = sum(1 for f in files for _ in f.open(encoding="utf-8")) - len(files)
        source = upload_to_internal_stage(cur, files)
        print(f"  {len(files)} files ({lines} lines) available in {source}")
        cur.execute(f"""
            COPY INTO {BRONZE}.CONSUMPTION_RAW FROM {source}
            PATTERN = '.*[.]csv'
            FILE_FORMAT = (FORMAT_NAME = '{BRONZE}.FF_CSV_HEADER')
            MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
            INCLUDE_METADATA = (_source_file = METADATA$FILENAME,
                                _file_row_number = METADATA$FILE_ROW_NUMBER,
                                _loaded_at = METADATA$START_SCAN_TIME)
            ON_ERROR = CONTINUE
            {'FORCE = TRUE' if force else ''}""")
        cols = [c[0].lower() for c in cur.description]
        results = [dict(zip(cols, r)) for r in cur.fetchall()]
        loaded = sum(int(r.get("rows_loaded") or 0) for r in results)
        for r in results:
            if "file" in r:
                print(f"    {r['file']}: {r['status']}, {r.get('rows_loaded')} rows, {r.get('errors_seen')} errors")
            else:
                print(f"    {r}")
        cur.execute(f"UPDATE {BRONZE}.CONSUMPTION_RAW SET _batch_id = %s WHERE _batch_id IS NULL", (batch_id,))
        return lines, loaded
    return body


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="reload files already loaded (incident demo)")
    run_job("s2_consumption_files", make_body(ap.parse_args().force))
