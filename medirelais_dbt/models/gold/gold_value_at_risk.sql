-- USE CASE 1 - Metric 1: stock value expiring within the next 90 days
-- Grain: batch x hospital x snapshot day
-- Excluded: narcotics, recalled batches, already expired batches
SELECT
    snapshot_date,
    hospital_id,
    hospital_name,
    product_id,
    product_name,
    batch_id,
    qty_on_hand,
    unit_cost_eur,
    stock_value_eur                                   AS value_at_risk_eur,
    expiry_date,
    days_to_expiry,
    is_cold_chain,
    -- Transfer rules: at least 30 days left and worth at least 200 EUR
    (days_to_expiry >= 30 AND stock_value_eur >= 200) AS is_transferable
FROM {{ ref('silver_stock') }}
WHERE days_to_expiry <= 90
  AND NOT is_expired
  AND NOT is_narcotic
  AND NOT is_recalled
