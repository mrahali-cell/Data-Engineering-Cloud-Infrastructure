{{ config(severity='warn') }}
-- README (airflow): over 15 % of tonight's rows rejected -> the day is broken.
-- Same rule as airflow/tasks/quality_gate.py: consumption of the latest delivery + stock rows
-- changed by the latest S1 run, pooled. Duplicates and used-up batches are not errors.
-- WARN only: the Airflow quality_gate is what stops gold (incident demo 1 stays the same).
-- The test FAILS (warns) if this query returns a row.
WITH cons AS (
    SELECT REGEXP_SUBSTR(_source, 'dt=([0-9-]+)', 1, 1, 'e', 1) AS delivery, reject_reason
    FROM {{ ref('silver_consumption_checked') }}
),
stock AS (
    SELECT _batch_id, _loaded_at, reject_reason FROM {{ ref('silver_stock_checked') }}
),
tonight AS (
    SELECT reject_reason FROM cons WHERE delivery = (SELECT MAX(delivery) FROM cons)
    UNION ALL
    SELECT reject_reason FROM stock
    WHERE _batch_id = (SELECT _batch_id FROM stock ORDER BY _loaded_at DESC LIMIT 1)
),
rate AS (
    SELECT COUNT(*) AS rows_received,
           COUNT_IF(reject_reason IS NOT NULL
                    AND reject_reason NOT IN ('duplicate_row', 'zero_quantity')) AS rows_rejected
    FROM tonight
)
SELECT rows_received, rows_rejected, rows_rejected / NULLIF(rows_received, 0) AS reject_rate
FROM rate
WHERE rows_rejected / NULLIF(rows_received, 0) > 0.15
