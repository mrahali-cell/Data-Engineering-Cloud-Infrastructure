"""Shared helpers for every ingestion job: Snowflake connection and the run log.

Settings come from environment variables (see .env.example). Secrets are never in the code:
the private key is a file mounted at run time (keys/rsa_key.p8).
"""
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization

DB = os.environ.get("SNOWFLAKE_DATABASE", "MEDIRELAIS")
BRONZE = f"{DB}.BRONZE"
STAGE = f"{BRONZE}.RAW_STAGE"
RUN_LOG = f"{BRONZE}.LOAD_RUNS"


def connect():
    key_path = Path(os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", "keys/rsa_key.p8"))
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()),
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "MEDIRELAIS_WH"),
        database=DB,
        schema="BRONZE",
    )


def new_batch_id(job):
    """One id per run, written on every row it loads: makes replay and debugging possible."""
    return f"{job}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def log_run(cur, job, batch_id, status, rows_in=0, rows_loaded=0, message=""):
    cur.execute(
        f"INSERT INTO {RUN_LOG} (run_at, job, batch_id, status, rows_in, rows_loaded, message) "
        "SELECT CURRENT_TIMESTAMP(), %s, %s, %s, %s, %s, %s",
        (job, batch_id, status, rows_in, rows_loaded, message[:1000]),
    )


def with_retries(func, attempts=3, delay=5, what="call"):
    """Retry a flaky call (network, API) a few times, then fail loudly."""
    for i in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:                          # noqa: BLE001 - we re-raise after the last try
            if i == attempts:
                raise
            print(f"  {what} failed ({exc}); retry {i}/{attempts - 1} in {delay}s")
            time.sleep(delay)


def run_job(job, body):
    """Run a job body(cur, batch_id) -> (rows_in, rows_loaded); log success or failure in LOAD_RUNS."""
    batch_id = new_batch_id(job)
    con = connect()
    cur = con.cursor()
    try:
        rows_in, rows_loaded = body(cur, batch_id)
        log_run(cur, job, batch_id, "SUCCESS", rows_in, rows_loaded)
        print(f"[{job}] OK: {rows_in} rows read, {rows_loaded} rows loaded (batch {batch_id})")
    except Exception as exc:
        try:
            log_run(cur, job, batch_id, "FAILED", message=str(exc))
        finally:
            print(f"[{job}] FAILED: {exc}", file=sys.stderr)
        raise
    finally:
        cur.close()
        con.close()
