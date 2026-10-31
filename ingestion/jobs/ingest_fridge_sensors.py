"""S5 · Fridge temperature sensors -> Snowflake bronze. Method: JSON MICRO-BATCHES.

Each fridge sends a reading every 5 minutes; the readings arrive as JSON-lines files.
Why this method: the cold-chain check (use case 3) runs every 15 minutes, not every second,
so small batches of files are enough; real streaming (Kafka, Snowpipe Streaming) would add
cost and complexity for no business gain. In production the same COPY would be a Snowpipe
with auto-ingest on the bucket.

Raw events are kept untouched in a VARIANT column: some sensor firmwares send other key names
(TEMP instead of temp_c, an epoch "timestamp" instead of "ts"); silver handles both.
Re-running is safe: COPY skips files it already loaded.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BRONZE, STAGE, run_job  # noqa: E402

LANDING = Path(os.environ.get("LANDING_DIR", "landing")) / "sensors"


def body(cur, batch_id):
    files = sorted(LANDING.glob("dt=*/*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no files in {LANDING}: run generate_sources.py first")
    events = sum(1 for f in files for _ in f.open(encoding="utf-8"))
    for f in files:
        cur.execute(f"PUT 'file://{f.resolve()}' @{STAGE}/sensors/{f.parent.name}/ "
                    "AUTO_COMPRESS = TRUE OVERWRITE = FALSE")
    cur.execute(f"""
        COPY INTO {BRONZE}.FRIDGE_READINGS_RAW (payload, _source_file, _file_row_number, _loaded_at, _batch_id)
        FROM (SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, CURRENT_TIMESTAMP(), '{batch_id}'
              FROM @{STAGE}/sensors/)
        FILE_FORMAT = (FORMAT_NAME = '{BRONZE}.FF_JSON') ON_ERROR = CONTINUE""")
    loaded = sum(int(r[3] or 0) for r in cur.fetchall() if len(r) > 3)
    print(f"  {len(files)} files, {events} events available, {loaded} newly loaded")
    return events, loaded


if __name__ == "__main__":
    run_job("s5_fridge_sensors", body)
