-- USE CASE 1 - the action: for each transferable batch, the hospital that
-- uses the most of this product (and can use it before it expires)
WITH at_risk AS (
    SELECT * FROM {{ ref('gold_value_at_risk') }}
    WHERE is_transferable
),
usage AS (
    SELECT hospital_id, product_id, hospital_name, avg_daily_use
    FROM {{ ref('gold_days_of_cover') }}
)
SELECT
    r.snapshot_date,
    r.batch_id,
    r.product_name,
    r.hospital_name                                   AS from_hospital,
    u.hospital_name                                   AS to_hospital,
    r.qty_on_hand,
    r.value_at_risk_eur,
    r.days_to_expiry,
    u.avg_daily_use                                   AS to_hospital_daily_use,
    ROUND(r.qty_on_hand / u.avg_daily_use, 0)         AS days_to_use_it_all,
    r.qty_on_hand / u.avg_daily_use <= r.days_to_expiry AS can_use_before_expiry
FROM at_risk r
JOIN usage u
  ON r.product_id   = u.product_id
 AND r.hospital_id <> u.hospital_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY r.batch_id ORDER BY u.avg_daily_use DESC) = 1
