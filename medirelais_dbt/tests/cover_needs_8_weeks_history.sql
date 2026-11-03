-- README: days of cover excludes "products with less than 8 weeks of history".
-- The test FAILS with one row per hospital x product shown with under 56 days of history.
SELECT c.snapshot_date, c.hospital_id, c.product_id, u.days_of_history
FROM {{ ref('gold_days_of_cover') }} c
JOIN {{ ref('silver_daily_use') }} u
  ON u.snapshot_date = c.snapshot_date
 AND u.hospital_id   = c.hospital_id
 AND u.product_id    = c.product_id
WHERE u.days_of_history < 56
