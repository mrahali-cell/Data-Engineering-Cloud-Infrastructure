# MédiRelais ingestion image: the source simulator + the 6 ingestion jobs.
# One image, one command per job, so an orchestrator (Airflow) can run each job as its own task.
#   docker build -t medirelais-ingest:1.0.0 .
FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Libraries first: this layer is cached as long as requirements.txt does not change
COPY requirements.txt .
RUN pip install -r requirements.txt

# Then the code only: no data, no .env, no keys (see .dockerignore)
COPY common.py generate_sources.py run_all.py make_key.py ./
COPY jobs/ jobs/
COPY sql/ sql/

# Never run as root
RUN useradd --create-home --uid 1000 medirelais \
    && mkdir -p /app/landing /app/keys && chown medirelais /app/landing /app/keys
USER medirelais

CMD ["python", "run_all.py", "--help"]
