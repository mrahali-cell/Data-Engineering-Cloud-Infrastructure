-- USE CASE 2: how many days the current stock lasts at the normal pace
-- Grain: product x hospital x snapshot day
-- Excluded: products with less than 8 weeks (56 days) of consumption history,
--           and products with zero consumption over the last 28 days
-- Alert: assumes the pharmacy uses its soonest-expiring batch first. A batch
-- expires unused when everything queued before it, plus the batch itself,
-- takes longer to use than the batch has left. (Comparing total cover with the
-- earliest expiry wrongly flagged a small batch sitting next to a long-dated one.)
WITH batches AS (
    SELECT
        s.snapshot_date,
        s.hospital_id,
        s.hospital_name,
        s.product_id,
        s.product_name,
        s.qty_on_hand,
        s.days_to_expiry,
        s.unit_cost_eur,
        u.avg_daily_use,
        SUM(s.qty_on_hand) OVER (
            PARTITION BY s.snapshot_date, s.hospital_id, s.product_id
            ORDER BY s.expiry_date, s.batch_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS qty_queued_up_to_this_batch
    FROM {{ ref('silver_stock') }} s
    JOIN {{ ref('silver_daily_use') }} u
      ON s.snapshot_date = u.snapshot_date
     AND s.hospital_id   = u.hospital_id
     AND s.product_id    = u.product_id
    WHERE NOT s.is_expired
      AND u.avg_daily_use > 0
      AND u.days_of_history >= 56
)
SELECT
    snapshot_date,
    hospital_id,
    hospital_name,
    product_id,
    product_name,
    SUM(qty_on_hand)                                  AS qty_on_hand,
    ROUND(MAX(avg_daily_use), 1)                      AS avg_daily_use,
    ROUND(SUM(qty_on_hand) / MAX(avg_daily_use), 0)   AS days_of_cover,
    MIN(days_to_expiry)                               AS min_days_to_expiry,
    -- Alert: some of this stock will expire before it is used
    MAX(CASE WHEN qty_queued_up_to_this_batch / avg_daily_use > days_to_expiry
             THEN 1 ELSE 0 END) = 1                   AS is_overstock_alert,
    -- Over-stock value: units that will expire before use at the current pace x unit cost
    ROUND(SUM(LEAST(qty_on_hand,
                    GREATEST(0, qty_queued_up_to_this_batch - avg_daily_use * days_to_expiry))
              * unit_cost_eur), 2)                    AS overstock_value_eur
FROM batches
GROUP BY 1, 2, 3, 4, 5
