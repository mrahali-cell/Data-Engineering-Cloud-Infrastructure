# MédiRelais · Airflow image = the official Airflow image + a separate Python environment for our jobs.
# Built from the repository root (see docker-compose.yml: context ..), so it can read ingestion/requirements.txt.
#
# Why a separate environment (ingest-venv): the ingestion jobs pin their own library versions
# (snowflake-connector-python, cryptography...). Installing them into Airflow's own Python could break
# Airflow, so they get their own toolbox. Airflow runs them with /opt/airflow/ingest-venv/bin/python.
FROM apache/airflow:3.1.8-python3.12

COPY ingestion/requirements.txt /tmp/ingestion-requirements.txt
RUN python -m venv /opt/airflow/ingest-venv \
    && /opt/airflow/ingest-venv/bin/pip install --no-cache-dir -r /tmp/ingestion-requirements.txt

# The code (ingestion/, airflow/dags, airflow/tasks) is NOT copied: it is mounted at run time,
# so a git pull is picked up without rebuilding. Only a change to ingestion/requirements.txt needs a rebuild.
