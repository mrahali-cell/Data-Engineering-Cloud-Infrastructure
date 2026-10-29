-- Business rule test: a suggested transfer must have at least 30 days left
-- and be worth at least 200 EUR. The test FAILS if this query returns rows.
SELECT *
FROM {{ ref('gold_transfer_suggestions') }}
WHERE days_to_expiry < 30
   OR value_at_risk_eur < 200
