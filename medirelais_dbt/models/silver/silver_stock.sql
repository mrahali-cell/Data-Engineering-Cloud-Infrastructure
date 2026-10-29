-- One row per batch on the shelf, enriched with product and hospital info
SELECT
    s.snapshot_date,
    s.hospital_id,
    h.hospital_name,
    s.product_id,
    p.product_name,
    p.category,
    s.batch_id,
    s.qty_on_hand,
    p.unit_cost_eur,
    s.qty_on_hand * p.unit_cost_eur                    AS stock_value_eur,
    s.expiry_date,
    DATEDIFF('day', s.snapshot_date, s.expiry_date)    AS days_to_expiry,
    p.is_cold_chain,
    p.is_narcotic,
    s.is_recalled,
    s.expiry_date < s.snapshot_date                    AS is_expired
FROM {{ source('bronze', 'stock') }} s
JOIN {{ source('bronze', 'products') }}  p ON s.product_id  = p.product_id
JOIN {{ source('bronze', 'hospitals') }} h ON s.hospital_id = h.hospital_id
WHERE s.qty_on_hand > 0
