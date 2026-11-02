-- One row per batch on the shelf per snapshot day, enriched with product and hospital info.
-- Rows that fail a check are not dropped silently: they go to silver_stock_quarantine.
SELECT
    snapshot_date,
    hospital_id,
    hospital_name,
    product_id,
    product_name,
    category,
    batch_id,
    qty_on_hand,
    unit_cost_eur,
    qty_on_hand * unit_cost_eur                    AS stock_value_eur,
    expiry_date,
    DATEDIFF('day', snapshot_date, expiry_date)    AS days_to_expiry,
    is_cold_chain,
    is_narcotic,
    is_recalled,
    expiry_date < snapshot_date                    AS is_expired,
    _batch_id,
    _loaded_at
FROM {{ ref('silver_stock_checked') }}
WHERE reject_reason IS NULL
