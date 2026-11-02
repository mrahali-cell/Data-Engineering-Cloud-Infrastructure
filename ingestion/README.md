# MédiRelais · ingestion (4 sources → Snowflake bronze)

One Docker image runs the hospital-side simulator and the 4 ingestion jobs.
Every job writes to `MEDIRELAIS.BRONZE`, adds `_source`/`_source_file`, `_loaded_at`, `_batch_id`
to each row, and logs its run (success or failure) in `MEDIRELAIS.BRONZE.LOAD_RUNS`.

| # | Source | Real? | Method | Bronze table(s) | Job |
|---|---|---|---|---|---|
| S1 | Pharmacy stock system (Postgres) | simulated, messy | incremental pull on `updated_at` + `MERGE` | `HOSPITALS_RAW`, `PRODUCTS_RAW`, `STOCK_RAW` | `jobs/ingest_stock_postgres.py` |
| S2 | Daily consumption files | simulated, messy | batch files → stage (GCS or internal) → `COPY INTO`, columns by name | `CONSUMPTION_RAW` | `jobs/ingest_consumption_files.py` |
| S3 | BDPM public drug database: medicines, boxes and their molecules | **real** | weekly download, full refresh | `BDPM_SPECIALITES_RAW`, `BDPM_PRESENTATIONS_RAW`, `BDPM_COMPOSITION_RAW` | `jobs/ingest_bdpm.py` |
| S4 | BDPM shortages file | **real** | daily pull, change detection (row hash + `MERGE`) | `SHORTAGES_RAW` | `jobs/ingest_shortages.py` |

The project keeps use cases 1 and 2 only, so the fridge sensors (S5, cold chain) and the weather API (S6) were
removed on 2 Nov 2026. Their old bronze tables are no longer read.

`generate_sources.py` plays the 12 hospitals: one run = one day. It damages about 4 % of the values on purpose
(mixed date formats, `N/A`, negative or impossible quantities, unknown codes, duplicate lines,
a renamed column from day 3) and writes the answer key to `landing/issues/day_N.json`.

## Run it

```bash
cp .env.example .env                 # fill in, never commit
mkdir -p keys                        # put rsa_key.p8 here (key-pair login, no password)
docker compose up -d pharmacy-db     # the hospitals' stock database
docker compose run --rm ingest python run_all.py --day 1     # simulate day 1 + load the 4 sources
docker compose run --rm ingest python run_all.py --day 2     # next day: only changes travel
```

Incident demos:

```bash
docker compose run --rm ingest python run_all.py --day 3 --incident corrupted     # ~40 % broken rows
docker compose run --rm ingest python jobs/ingest_consumption_files.py --force    # same files loaded twice
```

Check in Snowflake:

```sql
SELECT * FROM MEDIRELAIS.BRONZE.LOAD_RUNS ORDER BY run_at DESC;
```

## Notes

- S3 and S4 come from base-donnees-publique.medicaments.gouv.fr (open licence). Bronze keeps their columns by position
  (`c1`, `c2`...); silver names them using the official format description.
- The composition file (`CIS_COMPO_bdpm.txt`) gives the molecules of each medicine. Silver uses it to link our products
  to every medicine that contains the same molecule, whatever its brand name (Doliprane → paracetamol).
- S2 uses Snowflake's internal stage by default. To land the files in Google Cloud Storage instead, create the bucket,
  run `sql/gcs_stage.sql`, then set `GCS_BUCKET` and `GOOGLE_APPLICATION_CREDENTIALS` in `.env`.
- Re-running any job is safe: `MERGE` on keys, and `COPY` skips files it already loaded.
