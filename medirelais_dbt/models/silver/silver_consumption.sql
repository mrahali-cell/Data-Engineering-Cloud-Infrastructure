-- One row per hospital x product x day (clean, no negative quantities)
SELECT
    consumption_date,
    hospital_id,
    product_id,
    qty_used
FROM {{ source('bronze', 'consumption') }}
WHERE qty_used >= 0
