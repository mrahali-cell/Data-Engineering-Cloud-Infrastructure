"""S4 · Real medicine shortages (BDPM availability file) -> Snowflake bronze.
Method: DAILY PULL WITH CHANGE DETECTION (row hash + MERGE).

Source: CIS_CIP_Dispo_Spec.txt on base-donnees-publique.medicaments.gouv.fr ("Fichier des
ruptures de stocks"): which medicines are out of stock or under supply tension, since when.

Why this method: the file is republished as a full list, but only a few lines change each day.
We hash every line: new hash -> new row (first_seen_at = now); hash seen again -> last_seen_at
is updated; hash no longer in the file -> still_listed = FALSE (the shortage ended).
That keeps the full history of each shortage without ever duplicating a line.
Business use: a medicine in national shortage must not be wasted, so its batches at risk of
expiring are offered to the network first (silver_product_reference, gold_transfer_suggestions).
"""
import hashlib
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BRONZE, STAGE, run_job, with_retries  # noqa: E402

URL = "https://base-donnees-publique.medicaments.gouv.fr/download/file/CIS_CIP_Dispo_Spec.txt"
WORK = Path(os.environ.get("LANDING_DIR", "landing")) / "shortages"


def fetch():
    def call():
        r = requests.get(URL, timeout=60)
        r.raise_for_status()
        return r.content
    raw = with_retries(call, what="download shortages file")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def body(cur, batch_id):
    lines = [line for line in fetch().splitlines() if line.strip()]
    print(f"  {len(lines)} lines; first: {lines[0][:110] if lines else '(empty)'}")
    # line -> 10 positional columns + its hash
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "shortages_today.tsv"
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            cols = (line.split("\t") + [""] * 10)[:10]
            f.write("\t".join(cols + [hashlib.sha256(line.encode()).hexdigest()]) + "\n")
    cur.execute(f"PUT 'file://{path.resolve()}' @{STAGE}/shortages/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE")
    cur.execute("CREATE OR REPLACE TEMPORARY TABLE TMP_SHORTAGES "
                "(c1 VARCHAR, c2 VARCHAR, c3 VARCHAR, c4 VARCHAR, c5 VARCHAR, c6 VARCHAR, c7 VARCHAR, "
                "c8 VARCHAR, c9 VARCHAR, c10 VARCHAR, row_hash VARCHAR)")
    cur.execute(f"COPY INTO TMP_SHORTAGES FROM @{STAGE}/shortages/shortages_today.tsv "
                f"FILE_FORMAT = (FORMAT_NAME = '{BRONZE}.FF_TSV_RAW') FORCE = TRUE")
    cur.execute(f"""
        MERGE INTO {BRONZE}.SHORTAGES_RAW t
        USING (SELECT DISTINCT * FROM TMP_SHORTAGES) s ON t.row_hash = s.row_hash
        WHEN MATCHED THEN UPDATE SET t.last_seen_at = CURRENT_TIMESTAMP(), t.still_listed = TRUE
        WHEN NOT MATCHED THEN INSERT (c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, row_hash,
                                      first_seen_at, last_seen_at, still_listed, _source_file, _batch_id)
             VALUES (s.c1, s.c2, s.c3, s.c4, s.c5, s.c6, s.c7, s.c8, s.c9, s.c10, s.row_hash,
                     CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), TRUE, 'CIS_CIP_Dispo_Spec.txt', %s)""",
                (batch_id,))
    inserted, updated = cur.fetchone()
    cur.execute(f"UPDATE {BRONZE}.SHORTAGES_RAW SET still_listed = FALSE "
                f"WHERE still_listed AND row_hash NOT IN (SELECT row_hash FROM TMP_SHORTAGES)")
    ended = cur.fetchone()[0]
    print(f"    new shortage lines: {inserted}, still listed: {updated}, no longer listed: {ended}")
    return len(lines), inserted


if __name__ == "__main__":
    run_job("s4_shortages", body)
