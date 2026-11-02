{{ config(materialized='ephemeral') }}
-- Every bronze consumption row (S2), cleaned and typed, with the reason it is rejected (NULL = clean).
-- silver_consumption keeps the clean rows, silver_consumption_quarantine keeps the rest.
--
-- Schema drift: from day 3 the files call the column quantity_used instead of qty_used.
-- COPY matches columns by name, so each name lands in its own bronze column and we
-- simply take whichever one is filled.
WITH typed AS (
    SELECT
        c.consumption_date                             AS raw_consumption_date,
        COALESCE(c.qty_used, c.quantity_used)          AS raw_qty_used,
        c.hospital_id                                  AS raw_hospital_id,
        c.product_id                                   AS raw_product_id,
        {{ clean_date('c.consumption_date') }}         AS consumption_date,
        {{ clean_code('c.hospital_id') }}              AS hospital_id,
        {{ clean_code('c.product_id') }}               AS product_id,
        {{ clean_quantity('COALESCE(c.qty_used, c.quantity_used)') }} AS qty_used,
        c._source_file                                 AS _source,
        c._file_row_number,
        c._loaded_at,
        c._batch_id
    FROM {{ source('bronze', 'consumption_raw') }} c
),
-- What a normal day looks like for each product, to catch impossible values (x1000 typos)
typical AS (
    SELECT product_id, MEDIAN(qty_used) AS median_qty
    FROM typed
    WHERE qty_used > 0
    GROUP BY product_id
),
checked AS (
    SELECT
        t.*,
        CASE
            WHEN t.consumption_date IS NULL                    THEN 'bad_date'
            WHEN {{ is_placeholder_date('t.consumption_date') }} THEN 'placeholder_date'
            WHEN h.hospital_id      IS NULL                    THEN 'unknown_hospital'
            WHEN p.product_id       IS NULL                    THEN 'unknown_product'
            WHEN t.qty_used         IS NULL                    THEN 'bad_quantity'
            WHEN t.qty_used         < 0                        THEN 'negative_quantity'
            WHEN t.qty_used         > 50 * ty.median_qty       THEN 'implausible_quantity'
        END AS failed_check
    FROM typed t
    LEFT JOIN {{ ref('silver_hospitals') }} h ON t.hospital_id = h.hospital_id
    LEFT JOIN {{ ref('silver_products') }}  p ON t.product_id  = p.product_id
    LEFT JOIN typical                       ty ON t.product_id = ty.product_id
)
SELECT
    *,
    -- the same hospital, product and day received twice (a duplicated line in a file, or the
    -- same file loaded twice): the latest valid load wins, a broken row never pushes out a good one
    COALESCE(failed_check,
        CASE WHEN ROW_NUMBER() OVER (
                      PARTITION BY consumption_date, hospital_id, product_id, failed_check IS NULL
                      ORDER BY _loaded_at DESC, _source, _file_row_number DESC) > 1
             THEN 'duplicate_row' END) AS reject_reason
FROM checked
