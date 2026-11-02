-- Business rule test: every suggested transfer must follow the README transfer rules:
-- at least 30 days left, worth at least 200 EUR, never a narcotic, a recalled or an
-- expired batch, never to the same hospital, and a cold-chain medicine only between two
-- hospitals whose fridges stayed between 2 and 8 °C (silver_cold_chain_status).
-- The test FAILS if this query returns rows.
SELECT t.*
FROM {{ ref('gold_transfer_suggestions') }} t
JOIN {{ ref('silver_stock') }} s
  ON s.snapshot_date = t.snapshot_date
 AND s.batch_id      = t.batch_id
LEFT JOIN {{ ref('silver_cold_chain_status') }} cf
  ON cf.snapshot_date = t.snapshot_date
 AND cf.hospital_id   = t.from_hospital_id
LEFT JOIN {{ ref('silver_cold_chain_status') }} ct
  ON ct.snapshot_date = t.snapshot_date
 AND ct.hospital_id   = t.to_hospital_id
WHERE t.days_to_expiry < 30
   OR t.value_at_risk_eur < 200
   OR s.is_narcotic
   OR s.is_recalled
   OR s.is_expired
   OR t.from_hospital_id = t.to_hospital_id
   OR (s.is_cold_chain AND NOT (COALESCE(cf.cold_chain_ok, FALSE) AND COALESCE(ct.cold_chain_ok, FALSE)))
