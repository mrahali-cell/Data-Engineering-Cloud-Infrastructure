{{ config(schema='GOLD') }}
-- Quality of the latest night, for the dashboard tile. Same rule as airflow/tasks/quality_gate.py.
-- In the silver folder so it is built with silver, BEFORE the gate: fresh even when gold is blocked.
-- Written to GOLD because the dashboard role (MEDIRELAIS_READER) reads GOLD only.
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
)
SELECT
    (SELECT MAX(delivery) FROM cons)::DATE                       AS delivery_date,
    COUNT(*)                                                     AS rows_received,
    COUNT_IF(reject_reason IS NOT NULL
             AND reject_reason NOT IN ('duplicate_row', 'zero_quantity')) AS rows_rejected,
    rows_rejected / NULLIF(rows_received, 0)                     AS reject_rate,
    reject_rate > 0.15                                           AS gold_blocked
FROM tonight