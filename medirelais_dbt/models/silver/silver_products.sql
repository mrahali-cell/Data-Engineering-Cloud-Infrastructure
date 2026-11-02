-- One row per product (S1, already typed in the source database).
-- If the product was loaded more than once, the latest load wins.
SELECT
    {{ clean_code('product_id') }} AS product_id,
    product_name,
    category,
    unit_cost_eur,
    is_cold_chain,
    is_narcotic,
    match_keyword        -- the word used to find the product in the real BDPM database (S3)
FROM {{ source('bronze', 'products_raw') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY {{ clean_code('product_id') }} ORDER BY _loaded_at DESC) = 1
