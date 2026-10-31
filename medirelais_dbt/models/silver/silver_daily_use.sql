-- Average daily use per hospital x product, over the 28 days before each stock snapshot.
-- The window is anchored on each snapshot's own date, with an upper bound, so
-- re-running an old day gives the same answer (it used to be MAX(snapshot_date)).
-- Grain: snapshot day x hospital x product. Feeds days of cover and transfer receivers.
WITH snapshots AS (
    SELECT DISTINCT snapshot_date FROM {{ ref('silver_stock') }}
),
first_use AS (
    SELECT hospital_id, product_id, MIN(consumption_date) AS first_consumption_date
    FROM {{ ref('silver_consumption') }}
    GROUP BY 1, 2
)
SELECT
    d.snapshot_date,
    c.hospital_id,
    c.product_id,
    SUM(c.qty_used) / 28.0                                       AS avg_daily_use,
    COUNT(DISTINCT c.consumption_date)                           AS days_reported,
    DATEDIFF('day', f.first_consumption_date, d.snapshot_date)   AS days_of_history
FROM snapshots d
JOIN {{ ref('silver_consumption') }} c
  ON c.consumption_date >= d.snapshot_date - 28
 AND c.consumption_date <  d.snapshot_date
JOIN first_use f
  ON f.hospital_id = c.hospital_id
 AND f.product_id  = c.product_id
GROUP BY d.snapshot_date, c.hospital_id, c.product_id, f.first_consumption_date
