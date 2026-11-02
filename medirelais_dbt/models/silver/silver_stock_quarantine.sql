-- Stock rows that failed a check, kept exactly as received, with the reason.
SELECT
    reject_reason,
    snapshot_date,
    raw_hospital_id   AS hospital_id,
    raw_product_id    AS product_id,
    batch_id,
    raw_qty_on_hand   AS qty_on_hand,
    raw_expiry_date   AS expiry_date,
    raw_is_recalled   AS is_recalled,
    _source,
    _loaded_at,
    _batch_id
FROM {{ ref('silver_stock_checked') }}
WHERE reject_reason IS NOT NULL
