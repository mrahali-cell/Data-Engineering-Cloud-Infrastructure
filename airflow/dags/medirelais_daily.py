"""
### MédiRelais · daily pipeline

Every morning at 06:00 (Paris): simulate the hospitals' night, load the 4 sources into BRONZE,
check the loads, build SILVER, check data quality, build GOLD, report.

**Fault tolerance**
- each task is retried before it is declared failed (network glitches fix themselves);
- a failed task stops everything after it (`upstream_failed`): bad or incomplete data never reaches gold;
- `check_ingestion` stops the run if a source is missing; `quality_gate` stops it if too many of tonight's
  rows were rejected, so the dashboard keeps yesterday's good results;
- after a fix, **Clear** the failed task: the run resumes from there, finished tasks are not redone.

**Run it by hand:** Trigger with config, e.g. `{"day": 3, "incident": "corrupted"}`.
`day` empty = the next simulated day. Incident 3 (a source that is down): set the Variable
`shortages_url` to a wrong address, trigger, then delete the Variable and Clear the failed task.
"""
from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

PY = "/opt/airflow/ingest-venv/bin/python"     # the jobs' own Python environment (see airflow/Dockerfile)
INGESTION = "/opt/airflow/ingestion"            # ingestion/ of the repo, mounted
TASKS = "/opt/airflow/tasks"                    # airflow/tasks/ of the repo, mounted
RUN_START = "{{ dag_run.start_date }}"          # when this run started: the checks only look at this run

default_args = {
    "owner": "manel",
    "retries": 2,                               # try again twice before declaring the task failed
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=20), # a stuck task fails instead of blocking the morning
}

with DAG(
    dag_id="medirelais_daily",
    description="Hospitals' night -> 4 sources into bronze -> checks -> silver -> quality gate -> gold",
    schedule="0 6 * * *",                       # every day at 06:00, Europe/Paris
    start_date=pendulum.datetime(2026, 11, 1, tz="Europe/Paris"),
    catchup=False,                              # do not replay the days before today
    max_active_runs=1,                          # never two runs at the same time
    default_args=default_args,
    params={
        "day": Param(None, type=["null", "integer"], minimum=1,
                     description="Simulated day to generate (empty = the next one)"),
        "incident": Param("none", enum=["none", "corrupted"],
                          description="corrupted = about 40% of the day's rows broken (incident demo 1)"),
    },
    doc_md=__doc__,
    tags=["medirelais"],
) as dag:

    # 1. The hospitals' side: new stock movements in Postgres + tonight's consumption files.
    #    Not part of a real pipeline (real hospitals produce this); here it makes each run a new day.
    simulate_day = BashOperator(
        task_id="simulate_day",
        bash_command=f'{PY} {TASKS}/simulate_day.py --day "{{{{ params.day or \'\' }}}}" '
                     f'--incident "{{{{ params.incident }}}}"',
        retries=0,                              # deterministic: retrying would not change the outcome
    )

    # 2. Ingestion: the 4 jobs of ingestion/jobs, in parallel (they do not depend on each other).
    #    A job that fails exits with an error code -> the task fails -> Airflow retries it.
    ingest_s1_stock = BashOperator(
        task_id="ingest_s1_stock",
        bash_command=f"cd {INGESTION} && {PY} jobs/ingest_stock_postgres.py",
    )
    ingest_s2_consumption = BashOperator(
        task_id="ingest_s2_consumption",
        bash_command=f"cd {INGESTION} && {PY} jobs/ingest_consumption_files.py",
    )
    ingest_s3_bdpm = BashOperator(
        task_id="ingest_s3_bdpm",
        bash_command=f"cd {INGESTION} && {PY} jobs/ingest_bdpm.py",
    )
    ingest_s4_shortages = BashOperator(
        task_id="ingest_s4_shortages",
        bash_command=f"cd {INGESTION} && {PY} jobs/ingest_shortages.py",
        # Incident demo 3: an Airflow Variable "shortages_url" set to a wrong address = the source is down
        env={"SHORTAGES_URL": "{{ var.value.get('shortages_url', '') }}"},
        append_env=True,                        # keep the container's settings (Snowflake, paths)
    )
    ingestion = [ingest_s1_stock, ingest_s2_consumption, ingest_s3_bdpm, ingest_s4_shortages]

    # 3. Did all 4 sources load in THIS run, and did tonight's consumption files arrive?
    check_ingestion = BashOperator(
        task_id="check_ingestion",
        bash_command=f'{PY} {TASKS}/check_ingestion.py --since "{RUN_START}"',
        retries=0,                              # a missing source will not appear by retrying the check
    )

    # 4. dbt in Snowflake, first half: SILVER (cleaning, quarantine) and its tests
    dbt_silver = BashOperator(
        task_id="dbt_silver",
        bash_command=f'{PY} {TASKS}/run_dbt.py "build --select silver --indirect-selection cautious"',
        retries=1,
    )

    # 5. Quality gate: too many rejected rows tonight -> stop before gold
    quality_gate = BashOperator(
        task_id="quality_gate",
        bash_command=f"{PY} {TASKS}/quality_gate.py",
        retries=0,
    )

    # 6. dbt in Snowflake, second half: GOLD (value at risk, transfers, days of cover) and the business tests
    dbt_gold = BashOperator(
        task_id="dbt_gold",
        bash_command=f'{PY} {TASKS}/run_dbt.py "build --select gold"',
        retries=1,
    )

    # 7. What this run did, in one place (read it in the task's log)
    run_report = BashOperator(
        task_id="run_report",
        bash_command=f'{PY} {TASKS}/run_report.py --since "{RUN_START}"',
        retries=0,
    )

    simulate_day >> ingestion >> check_ingestion >> dbt_silver >> quality_gate >> dbt_gold >> run_report
