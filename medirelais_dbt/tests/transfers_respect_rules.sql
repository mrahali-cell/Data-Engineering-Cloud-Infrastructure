-- Business rule test: every suggested transfer must follow the README transfer rules:
-- at least 30 days left, worth at least 200 EUR, no cold-chain product without proof,
-- never a narcotic, a recalled or an expired batch, and never to the same hospital.
-- The test FAILS if this query returns rows.
SELECT t.*
FROM {{ ref('gold_transfer_suggestions') }} t
JOIN {{ ref('silver_stock') }} s
  ON s.snapshot_date = t.snapshot_date
 AND s.batch_id      = t.batch_id
WHERE t.days_to_expiry < 30
   OR t.value_at_risk_eur < 200
   OR s.is_cold_chain
   OR s.is_narcotic
   OR s.is_recalled
   OR s.is_expired
   OR t.from_hospital_id = t.to_hospital_id
