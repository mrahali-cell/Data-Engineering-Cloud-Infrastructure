-- Acceptance test (README): the business cases planted by ingestion/generate_sources.py
-- (seed 42) must come out as expected on the latest snapshot, whatever the simulated day.
-- The checks look at the planted hospital x product pairs, not at exact quantities,
-- because the pharmacy uses some stock every day.
-- Verified on the first full run of the 6 sources (2 Nov 2026, days 1-2, snapshot 2026-10-29):
-- 20 batches / 38,530.99 EUR at risk, 5 transfer suggestions, every check below passing.
-- The test FAILS if this query returns rows (one row per failed check).
WITH latest AS (
    SELECT MAX(snapshot_date) AS snapshot_date FROM {{ ref('silver_stock') }}
),
var AS (
    SELECT v.* FROM {{ ref('gold_value_at_risk') }} v JOIN latest l USING (snapshot_date)
),
cover AS (
    SELECT c.* FROM {{ ref('gold_days_of_cover') }} c JOIN latest l USING (snapshot_date)
),
transfers AS (
    SELECT t.* FROM {{ ref('gold_transfer_suggestions') }} t JOIN latest l USING (snapshot_date)
),
stock AS (
    SELECT s.* FROM {{ ref('silver_stock') }} s JOIN latest l USING (snapshot_date)
),
checks AS (
    SELECT 'UC1: some stock is at risk of expiring within 90 days' AS check_name,
           (SELECT COUNT(*) > 0 AND SUM(value_at_risk_eur) > 0 FROM var) AS passed
    UNION ALL
    SELECT 'UC1: H01 insulin glargine is at risk but blocked until cold-chain proof',
           (SELECT COUNT(*) >= 1 FROM var WHERE hospital_id = 'H01' AND product_id = 'P008'
               AND transfer_block_reason = 'no_cold_chain_proof')
    UNION ALL
    SELECT 'UC1: H02 rituximab is at risk but blocked until cold-chain proof',
           (SELECT COUNT(*) >= 1 FROM var WHERE hospital_id = 'H02' AND product_id = 'P020'
               AND transfer_block_reason = 'no_cold_chain_proof')
    UNION ALL
    SELECT 'UC1: H05 ceftriaxone with under 30 days left is not transferable',
           (SELECT COUNT(*) >= 1 FROM var WHERE hospital_id = 'H05' AND product_id = 'P006'
               AND transfer_block_reason = 'under_30_days')
    UNION ALL
    SELECT 'UC1: H10 furosemide worth under 200 EUR is not transferable',
           (SELECT COUNT(*) >= 1 FROM var WHERE hospital_id = 'H10' AND product_id = 'P015'
               AND transfer_block_reason = 'under_200_eur')
    UNION ALL
    SELECT 'UC1: narcotics (morphine) never appear, although H03 holds a batch',
           (SELECT COUNT(*) = 0 FROM var WHERE product_id = 'P004')
           AND (SELECT COUNT(*) >= 1 FROM stock WHERE hospital_id = 'H03' AND product_id = 'P004')
    UNION ALL
    SELECT 'UC1: the recalled H06 enoxaparin batch never appears',
           (SELECT COUNT(*) = 0 FROM var v JOIN stock s USING (batch_id) WHERE s.is_recalled)
           AND (SELECT COUNT(*) >= 1 FROM stock WHERE hospital_id = 'H06' AND product_id = 'P011' AND is_recalled)
    UNION ALL
    SELECT 'UC1: no expired batch appears',
           (SELECT COUNT(*) = 0 FROM var WHERE days_to_expiry < 0)
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
    SELECT 'UC2: H04 uses insulin glargine a lot, so it has cover data',
           (SELECT COUNT(*) = 1 FROM cover WHERE hospital_id = 'H04' AND product_id = 'P008' AND days_of_cover > 0)
)
SELECT check_name
FROM checks
WHERE NOT COALESCE(passed, FALSE)
