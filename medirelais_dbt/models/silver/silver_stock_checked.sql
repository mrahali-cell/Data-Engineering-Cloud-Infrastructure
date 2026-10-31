{{ config(materialized='ephemeral') }}
-- Every bronze stock row, typed, with the reason it is rejected (NULL = clean).
-- silver_stock keeps the clean rows, silver_stock_quarantine keeps the rest:
-- no row disappears without a reason.
WITH typed AS (
    SELECT
        s.snapshot_date                   AS raw_snapshot_date,
        s.qty_on_hand                     AS raw_qty_on_hand,
        s.expiry_date                     AS raw_expiry_date,
        s.is_recalled                     AS raw_is_recalled,
        TRY_TO_DATE(s.snapshot_date)      AS snapshot_date,
        s.hospital_id,
        s.product_id,
        s.batch_id,
        TRY_TO_NUMBER(s.qty_on_hand)      AS qty_on_hand,
        TRY_TO_DATE(s.expiry_date)        AS expiry_date,
        TRY_TO_BOOLEAN(s.is_recalled)     AS is_recalled,
        s._source,
        s._loaded_at,
        s._batch_id
    FROM {{ source('bronze', 'stock') }} s
),
checked AS (
    SELECT
        t.*,
        h.hospital_name,
        p.product_name,
        p.category,
        p.unit_cost_eur,
        p.is_cold_chain,
        p.is_narcotic,
        CASE
            WHEN t.snapshot_date IS NULL THEN 'bad_snapshot_date'
            WHEN t.batch_id      IS NULL THEN 'missing_batch_id'
            WHEN h.hospital_id   IS NULL THEN 'unknown_hospital'
            WHEN p.product_id    IS NULL THEN 'unknown_product'
            WHEN t.qty_on_hand   IS NULL THEN 'bad_quantity'
            WHEN t.qty_on_hand   < 0     THEN 'negative_quantity'
            WHEN t.qty_on_hand   = 0     THEN 'zero_quantity'
            WHEN t.expiry_date   IS NULL THEN 'bad_expiry_date'
            WHEN t.is_recalled   IS NULL THEN 'bad_recall_flag'
        END AS failed_check
    FROM typed t
    LEFT JOIN {{ ref('silver_hospitals') }} h ON t.hospital_id = h.hospital_id
    LEFT JOIN {{ ref('silver_products') }}  p ON t.product_id  = p.product_id
)
SELECT
    *,
    -- the same batch on the same day loaded twice: the latest valid load wins
    -- (a broken row arriving later never pushes out a good one)
    COALESCE(failed_check,
        CASE WHEN ROW_NUMBER() OVER (
                      PARTITION BY snapshot_date, batch_id, failed_check IS NULL
                      ORDER BY _loaded_at DESC, _source) > 1
             THEN 'duplicate_row' END) AS reject_reason
FROM checked
