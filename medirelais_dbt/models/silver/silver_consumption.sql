-- One row per hospital x product x day.
-- Rows that fail a check are not dropped silently: they go to silver_consumption_quarantine.
SELECT
    consumption_date,
    hospital_id,
    product_id,
    qty_used,
    _batch_id,
    _loaded_at
FROM {{ ref('silver_consumption_checked') }}
WHERE reject_reason IS NULL
