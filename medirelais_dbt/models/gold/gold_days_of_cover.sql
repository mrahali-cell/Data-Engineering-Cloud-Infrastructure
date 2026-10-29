-- USE CASE 2: how many days the current stock lasts at the normal pace
-- Grain: product x hospital x snapshot day
-- Excluded: products with zero consumption over the last 28 days
WITH stock AS (
    SELECT
        snapshot_date,
        hospital_id,
        hospital_name,
        product_id,
        product_name,
        SUM(qty_on_hand)    AS qty_on_hand,
        MIN(days_to_expiry) AS min_days_to_expiry
    FROM {{ ref('silver_stock') }}
    WHERE NOT is_expired
    GROUP BY 1, 2, 3, 4, 5
),
usage AS (
    SELECT
        c.hospital_id,
        c.product_id,
        SUM(c.qty_used) / 28.0 AS avg_daily_use
    FROM {{ ref('silver_consumption') }} c
    WHERE c.consumption_date >= (SELECT MAX(snapshot_date) FROM {{ ref('silver_stock') }}) - 28
    GROUP BY 1, 2
)
SELECT
    s.snapshot_date,
    s.hospital_id,
    s.hospital_name,
    s.product_id,
    s.product_name,
    s.qty_on_hand,
    ROUND(u.avg_daily_use, 1)                        AS avg_daily_use,
    ROUND(s.qty_on_hand / u.avg_daily_use, 0)        AS days_of_cover,
    s.min_days_to_expiry,
    -- Alert: the stock will last longer than its shelf life -> it will expire
    (s.qty_on_hand / u.avg_daily_use) > s.min_days_to_expiry AS is_overstock_alert
FROM stock s
JOIN usage u
  ON s.hospital_id = u.hospital_id
 AND s.product_id  = u.product_id
WHERE u.avg_daily_use > 0
