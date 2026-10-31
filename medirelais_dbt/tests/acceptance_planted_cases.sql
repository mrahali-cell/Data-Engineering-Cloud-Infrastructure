-- Acceptance test (README): the planted cases in generate_data.py (seed 42,
-- snapshot 2026-10-28) must come out exactly as expected. The expected figures
-- were checked by hand, outside dbt, straight from the CSV files.
-- The test FAILS if this query returns rows (one row per failed check).
WITH var AS (
    SELECT * FROM {{ ref('gold_value_at_risk') }} WHERE snapshot_date = DATE '2026-10-28'
),
cover AS (
    SELECT * FROM {{ ref('gold_days_of_cover') }} WHERE snapshot_date = DATE '2026-10-28'
),
transfers AS (
    SELECT * FROM {{ ref('gold_transfer_suggestions') }} WHERE snapshot_date = DATE '2026-10-28'
),
checks AS (
    SELECT 'UC1: total value at risk is 146,658.16 EUR over 20 batches' AS check_name,
           (SELECT ROUND(SUM(value_at_risk_eur), 2) = 146658.16 AND COUNT(*) = 20 FROM var) AS passed
    UNION ALL
    SELECT 'UC1: H01 insulin (220 pens) is at risk but blocked until cold-chain proof',
           (SELECT COUNT(*) = 1 FROM var WHERE hospital_id = 'H01' AND product_id = 'P008'
               AND qty_on_hand = 220 AND transfer_block_reason = 'no_cold_chain_proof')
    UNION ALL
    SELECT 'UC1: H02 rituximab (4 vials) is at risk but blocked until cold-chain proof',
           (SELECT COUNT(*) = 1 FROM var WHERE hospital_id = 'H02' AND product_id = 'P020'
               AND qty_on_hand = 4 AND transfer_block_reason = 'no_cold_chain_proof')
    UNION ALL
    SELECT 'UC1: H05 ceftriaxone with 20 days left is not transferable',
           (SELECT COUNT(*) = 1 FROM var WHERE hospital_id = 'H05' AND product_id = 'P006'
               AND qty_on_hand = 150 AND transfer_block_reason = 'under_30_days')
    UNION ALL
    SELECT 'UC1: H10 furosemide worth 6 EUR is not transferable',
           (SELECT COUNT(*) = 1 FROM var WHERE hospital_id = 'H10' AND product_id = 'P015'
               AND qty_on_hand = 100 AND transfer_block_reason = 'under_200_eur')
    UNION ALL
    SELECT 'UC1: narcotics (morphine) never appear',
           (SELECT COUNT(*) = 0 FROM var WHERE product_id = 'P004')
    UNION ALL
    SELECT 'UC1: the recalled H06 enoxaparin batch never appears',
           (SELECT COUNT(*) = 0 FROM var WHERE hospital_id = 'H06' AND product_id = 'P011' AND qty_on_hand = 400)
    UNION ALL
    SELECT 'UC1: the expired H09 omeprazole batch never appears',
           (SELECT COUNT(*) = 0 FROM var WHERE hospital_id = 'H09' AND product_id = 'P013' AND qty_on_hand = 500)
    UNION ALL
    SELECT 'UC1: no cold-chain batch is suggested for transfer',
           (SELECT COUNT(*) = 0 FROM transfers WHERE product_id IN ('P008', 'P009', 'P019', 'P020', 'P021', 'P022'))
    UNION ALL
    SELECT 'UC2: H03 paracetamol is flagged as over-stocked',
           (SELECT COUNT(*) = 1 FROM cover WHERE hospital_id = 'H03' AND product_id = 'P001' AND is_overstock_alert)
    UNION ALL
    SELECT 'UC2: H07 epoetin (zero use) is excluded from days of cover',
           (SELECT COUNT(*) = 0 FROM cover WHERE hospital_id = 'H07' AND product_id = 'P019')
    UNION ALL
    SELECT 'UC2: H12 albumin (less than 8 weeks of history) is excluded from days of cover',
           (SELECT COUNT(*) = 0 FROM cover WHERE hospital_id = 'H12' AND product_id = 'P023')
    UNION ALL
    SELECT 'UC2: 3 sample products match the manual cover (17, 45 and 41 days)',
           (SELECT COUNT(*) = 3 FROM cover WHERE
                   (hospital_id = 'H01' AND product_id = 'P001' AND days_of_cover = 17)
                OR (hospital_id = 'H04' AND product_id = 'P008' AND days_of_cover = 45)
                OR (hospital_id = 'H08' AND product_id = 'P024' AND days_of_cover = 41))
)
SELECT check_name
FROM checks
WHERE NOT COALESCE(passed, FALSE)
