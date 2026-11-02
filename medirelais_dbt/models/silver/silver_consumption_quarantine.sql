-- Consumption rows that failed a check, kept exactly as received, with the reason.
SELECT
    reject_reason,
    raw_consumption_date AS consumption_date,
    raw_hospital_id      AS hospital_id,
    raw_product_id       AS product_id,
    raw_qty_used         AS qty_used,
    _source,
    _file_row_number,
    _loaded_at,
    _batch_id
FROM {{ ref('silver_consumption_checked') }}
WHERE reject_reason IS NOT NULL
