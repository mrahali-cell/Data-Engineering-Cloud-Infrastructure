-- USE CASE 1 - Metric 1: stock value expiring within the next 90 days
-- Grain: batch x hospital x snapshot day
-- Excluded: narcotics, recalled batches, already expired batches
-- Transfer rules (README): at least 30 days left, worth at least 200 EUR, and
-- cold-chain products must prove they stayed between 2 and 8 °C. We have no
-- fridge data yet (use case 3), so cold-chain batches are blocked, with the reason shown.
WITH at_risk AS (
    SELECT
        snapshot_date,
        hospital_id,
        hospital_name,
        product_id,
        product_name,
        batch_id,
        qty_on_hand,
        unit_cost_eur,
        stock_value_eur                               AS value_at_risk_eur,
        expiry_date,
        days_to_expiry,
        is_cold_chain,
        CASE
            WHEN days_to_expiry < 30   THEN 'under_30_days'
            WHEN stock_value_eur < 200 THEN 'under_200_eur'
            WHEN is_cold_chain         THEN 'no_cold_chain_proof'
        END                                           AS transfer_block_reason
    FROM {{ ref('silver_stock') }}
    WHERE days_to_expiry <= 90
      AND NOT is_expired
      AND NOT is_narcotic
      AND NOT is_recalled
)
SELECT
    *,
    transfer_block_reason IS NULL AS is_transferable
FROM at_risk
