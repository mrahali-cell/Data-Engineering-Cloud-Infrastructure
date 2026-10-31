{{ config(materialized='ephemeral') }}
-- Every bronze consumption row, typed, with the reason it is rejected (NULL = clean).
-- silver_consumption keeps the clean rows, silver_consumption_quarantine keeps the rest.
WITH typed AS (
    SELECT
        c.consumption_date                AS raw_consumption_date,
        c.qty_used                        AS raw_qty_used,
        TRY_TO_DATE(c.consumption_date)   AS consumption_date,
        c.hospital_id,
        c.product_id,
        TRY_TO_NUMBER(c.qty_used)         AS qty_used,
        c._source,
        c._loaded_at,
        c._batch_id
    FROM {{ source('bronze', 'consumption') }} c
),
checked AS (
    SELECT
        t.*,
        CASE
            WHEN t.consumption_date IS NULL THEN 'bad_date'
            WHEN h.hospital_id      IS NULL THEN 'unknown_hospital'
            WHEN p.product_id       IS NULL THEN 'unknown_product'
            WHEN t.qty_used         IS NULL THEN 'bad_quantity'
            WHEN t.qty_used         < 0     THEN 'negative_quantity'
        END AS failed_check
    FROM typed t
    LEFT JOIN {{ ref('silver_hospitals') }} h ON t.hospital_id = h.hospital_id
    LEFT JOIN {{ ref('silver_products') }}  p ON t.product_id  = p.product_id
)
SELECT
    *,
    -- the same hospital, product and day loaded twice: the latest valid load wins
    -- (a broken row arriving later never pushes out a good one)
    COALESCE(failed_check,
        CASE WHEN ROW_NUMBER() OVER (
                      PARTITION BY consumption_date, hospital_id, product_id, failed_check IS NULL
                      ORDER BY _loaded_at DESC, _source) > 1
             THEN 'duplicate_row' END) AS reject_reason
FROM checked
