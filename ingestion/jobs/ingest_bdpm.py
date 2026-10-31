"""S3 · Real French public drug database (BDPM) -> Snowflake bronze. Method: BATCH DOWNLOAD, full refresh.

Source: base-donnees-publique.medicaments.gouv.fr (ANSM / HAS / Assurance maladie), open licence.
  CIS_bdpm.txt      one row per medicine ("spécialité"): code CIS, name, form, route, status...
  CIS_CIP_bdpm.txt  one row per box ("présentation"): code CIS, CIP13 barcode, label, price...

Why this method: reference data that changes a few times a month; a weekly full refresh is
simpler and safer than tracking changes. The files are tab-separated, without header, and
historically in Windows-1252: we convert them to UTF-8 before loading (accents stay correct).
Bronze keeps the columns by position (c1, c2, ...): silver names them, checked against the
official format description (Contenu_et_format_des_fichiers_telechargeables_dans_la_BDM_v5.pdf).
"""
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BRONZE, STAGE, run_job, with_retries  # noqa: E402

BASE = "https://base-donnees-publique.medicaments.gouv.fr/download/file/"
FILES = {"CIS_bdpm.txt": "BDPM_SPECIALITES_RAW", "CIS_CIP_bdpm.txt": "BDPM_PRESENTATIONS_RAW"}
WORK = Path(os.environ.get("LANDING_DIR", "landing")) / "bdpm"


def download(name):
    def call():
        r = requests.get(BASE + name, timeout=60)
        r.raise_for_status()
        return r.content
    raw = with_retries(call, what=f"download {name}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    path = WORK / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path, text.count("\n")


def body(cur, batch_id):
    total_in = total_loaded = 0
    for name, table in FILES.items():
        path, lines = download(name)
        first = path.read_text(encoding="utf-8").splitlines()[0]
        print(f"  {name}: {lines} lines, {first.count(chr(9)) + 1} columns, first line: {first[:100]}")
        cur.execute(f"PUT 'file://{path.resolve()}' @{STAGE}/bdpm/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE")
        cur.execute(f"TRUNCATE TABLE {BRONZE}.{table}")                 # weekly snapshot: replace
        cols = ", ".join(f"${i}" for i in range(1, 15))
        cur.execute(f"""
            COPY INTO {BRONZE}.{table}
            FROM (SELECT {cols}, METADATA$FILENAME, CURRENT_TIMESTAMP(), '{batch_id}'
                  FROM @{STAGE}/bdpm/{name})
            FILE_FORMAT = (FORMAT_NAME = '{BRONZE}.FF_TSV_RAW') ON_ERROR = CONTINUE FORCE = TRUE""")
        loaded = sum(int(r[3] or 0) for r in cur.fetchall() if len(r) > 3)
        print(f"    -> {table}: {loaded} rows")
        total_in += lines
        total_loaded += loaded
    return total_in, total_loaded


if __name__ == "__main__":
    run_job("s3_bdpm_reference", body)
