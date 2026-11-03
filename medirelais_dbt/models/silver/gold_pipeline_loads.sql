{{ config(schema='GOLD') }}
-- Pipeline tab of the team dashboard: one row per ingestion job run (BRONZE.LOAD_RUNS).
-- In the silver folder so it is rebuilt every night, even when the quality gate blocks gold.
-- Written to GOLD because the dashboard role (MEDIRELAIS_READER) reads GOLD only.
SELECT
    run_at,
    run_at::DATE                         AS run_date,
    job,
    batch_id,
    status,
    rows_in,
    rows_loaded,
    rows_in = rows_loaded                AS nothing_lost,
    message
FROM {{ source('bronze', 'load_runs') }}
