-- Consumption rows that failed a check, kept as received, with the reason.
SELECT
    reject_reason,
    raw_consumption_date AS consumption_date,
    hospital_id,
    product_id,
    raw_qty_used         AS qty_used,
    _source,
    _loaded_at,
    _batch_id
FROM {{ ref('silver_consumption_checked') }}
WHERE reject_reason IS NOT NULL
