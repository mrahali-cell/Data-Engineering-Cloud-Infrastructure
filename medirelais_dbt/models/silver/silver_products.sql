-- One row per product, typed from the all-text bronze table.
-- If the file was loaded more than once, the latest load wins.
SELECT
    product_id,
    product_name,
    category,
    TRY_TO_NUMBER(unit_cost_eur, 10, 2) AS unit_cost_eur,
    TRY_TO_BOOLEAN(is_cold_chain)       AS is_cold_chain,
    TRY_TO_BOOLEAN(is_narcotic)         AS is_narcotic
FROM {{ source('bronze', 'products') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY _loaded_at DESC) = 1
