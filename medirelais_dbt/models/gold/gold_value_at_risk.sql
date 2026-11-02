-- USE CASE 1 - Metric 1: stock value expiring within the next 90 days
-- Grain: batch x hospital x snapshot day
-- Excluded: narcotics, recalled batches, already expired batches
-- Transfer rules (README): at least 30 days left, worth at least 200 EUR, and
-- cold-chain products must prove they stayed between 2 and 8 °C: the sending hospital's
-- fridges (S5) must have stayed in range over the last 7 days (silver_cold_chain_status).
-- Medicines in national shortage (S4) are flagged: wasting them costs more, so they come first.
WITH at_risk AS (
    SELECT
        s.snapshot_date,
        s.hospital_id,
        s.hospital_name,
        s.product_id,
        s.product_name,
        batch_id,
        qty_on_hand,
        unit_cost_eur,
        stock_value_eur                               AS value_at_risk_eur,
        expiry_date,
        days_to_expiry,
        s.is_cold_chain,
        IFF(s.is_cold_chain, cc.cold_chain_issue, NULL) AS cold_chain_issue,
        COALESCE(r.is_national_shortage, FALSE)       AS is_national_shortage,
        r.shortage_status,
        CASE
            WHEN days_to_expiry < 30   THEN 'under_30_days'
            WHEN stock_value_eur < 200 THEN 'under_200_eur'
            WHEN s.is_cold_chain AND NOT COALESCE(cc.cold_chain_ok, FALSE) THEN 'no_cold_chain_proof'
        END                                           AS transfer_block_reason
    FROM {{ ref('silver_stock') }} s
    LEFT JOIN {{ ref('silver_cold_chain_status') }} cc
      ON cc.snapshot_date = s.snapshot_date
     AND cc.hospital_id   = s.hospital_id
    LEFT JOIN {{ ref('silver_product_reference') }} r
      ON r.product_id = s.product_id
    WHERE days_to_expiry <= 90
      AND NOT is_expired
      AND NOT is_narcotic
      AND NOT is_recalled
)
SELECT
    *,
    transfer_block_reason IS NULL AS is_transferable
FROM at_risk
