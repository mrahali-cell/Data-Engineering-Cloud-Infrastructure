# MédiRelais · orchestration with Airflow

Airflow is the conductor of the pipeline. It runs on the laptop (Docker) and, every morning at 06:00,
starts each step in order, waits for its answer, retries what fails, and stops everything after a step
that still fails, so bad or incomplete data never reaches the dashboard.

## The DAG `medirelais_daily`

```
                ┌ ingest_s1_stock ────────┐
                ├ ingest_s2_consumption ──┤
simulate_day ──►├ ingest_s3_bdpm ─────────┼──► check_ingestion ──► dbt_silver ──► quality_gate ──► dbt_gold ──► run_report
                └ ingest_s4_shortages ────┘
```

| Task | What it does | Fails when | Retries |
| --- | --- | --- | --- |
| `simulate_day` | Plays the hospitals' night: stock movements in Postgres, tonight's consumption files (`ingestion/generate_sources.py`) | The simulator crashes | 0 |
| `ingest_s1_stock` … `ingest_s4_shortages` | The 4 jobs of `ingestion/jobs/`, in parallel | The job ends with an error (source down, Snowflake refused…) | 2, 1 minute apart |
| `check_ingestion` | Reads `BRONZE.LOAD_RUNS`: each source's latest run since the DAG started must be SUCCESS, and S2 must have loaded rows | A source did not load, or tonight's files did not arrive | 0 |
| `dbt_silver` | `EXECUTE DBT PROJECT … build --select silver` in Snowflake: cleaning, quarantine, tests | A silver model or test fails | 1 |
| `quality_gate` | Share of tonight's rows (consumption delivery + stock changes) rejected by silver; duplicates and used-up batches are not errors | Over 15 % (a normal night: about 5 %; a corrupted night: about 45 %) | 0 |
| `dbt_gold` | `EXECUTE DBT PROJECT … build --select gold`: value at risk, transfers, days of cover, business tests | A gold model or test fails | 1 |
| `run_report` | Prints what the run did: loads, quarantine, transfer suggestions | — | 0 |

The scripts behind the tasks are in [`tasks/`](tasks/); they log in to Snowflake exactly like the ingestion
jobs (`ingestion/common.py`, key pair, settings from `ingestion/.env`).

**Fault tolerance in practice**

- A task that fails is retried; if it still fails it turns red, and every task after it is marked
  `upstream_failed` and does not run.
- `check_ingestion` stops the run before dbt when a source is missing; `quality_gate` stops it before gold
  when tonight's data is too broken. Gold, and so the dashboard, keep yesterday's good results.
- After fixing the cause, **Clear** the red task: the run resumes from there, the green tasks are not redone.

## Run it

Prerequisites: Docker Desktop running (4 GB of memory or more in Settings → Resources), `ingestion/.env`
and `ingestion/keys/rsa_key.p8` in place.

```bash
cd ingestion && docker compose up -d pharmacy-db      # the hospitals' database
cd ../airflow && docker compose up -d --build         # first time: builds the image (3-5 min)
```

Open http://localhost:8080, switch `medirelais_daily` on, then **Trigger**. Stop with `docker compose down`.
Once Airflow runs the pipeline, suspend the Snowflake task so there is only one conductor:
`ALTER TASK MEDIRELAIS.PUBLIC.DAILY_PIPELINE SUSPEND;`

## Incident demos

| Incident | How | What Airflow shows |
| --- | --- | --- |
| 1 · A corrupted day | Trigger with config `{"incident": "corrupted"}` | `quality_gate` red, `dbt_gold` and `run_report` not run: gold keeps yesterday's results |
| 2 · Files loaded twice | `cd ingestion && docker compose run --rm ingest python jobs/ingest_consumption_files.py --force`, then trigger | All green: silver keeps one copy of each line |
| 3 · A source that is down | Admin → Variables: add `shortages_url` = `https://example.invalid/x`, trigger | `ingest_s4_shortages` retried twice then red; everything after it waits. Delete the Variable, **Clear** the task: the run finishes green |

## Incident Results
### Results (tested 2 Nov 2026)

| Incident | Result | Proof |
| --- | --- | --- |
| 1 · Corrupted day | `quality_gate` red (≈45 %), gold not refreshed, dashboard kept day 3 | docs\Incident 1\failed_dag.png|
| 2 · Files loaded twice | All green. Bronze: day 1–2 files ×2. Silver: 0 duplicates | docs\Incident 2\Incident_2_check_2026-11-02-2235_bronze.csv, docs\Incident 2\silver_after_incident.png|

## Start the simulation again from a clean state

A rehearsed incident (or a day replayed by mistake) leaves broken rows in the simulated stock. To start over,
with no DAG run in progress, from the `airflow` folder:

```bash
docker compose exec airflow /opt/airflow/ingest-venv/bin/python /opt/airflow/ingestion/jobs/reset_demo.py --yes
```

It empties the hospitals' database, the landing files and the 4 simulated bronze tables (the public data, the run log
and the Airflow history are kept). Then trigger the DAG with `day` empty, once per day to replay: day 1, day 2, day 3...
