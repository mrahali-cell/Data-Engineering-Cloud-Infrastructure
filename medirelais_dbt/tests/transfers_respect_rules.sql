-- Business rule test: every suggested transfer must follow the README transfer rules:
-- at least 30 days left, worth at least 200 EUR, never a narcotic, a recalled or an
-- expired batch, never to the same hospital, never a cold-chain medicine (no fridge data to
-- prove the cold chain), and only when the receiver can use some of it before it expires
-- (never more than the batch holds).
-- The test FAILS if this query returns rows.
SELECT t.*
FROM {{ ref('gold_transfer_suggestions') }} t
JOIN {{ ref('silver_stock') }} s
  ON s.snapshot_date = t.snapshot_date
 AND s.batch_id      = t.batch_id
WHERE t.days_to_expiry < 30
   OR t.value_at_risk_eur < 200
   OR s.is_narcotic
   OR s.is_recalled
   OR s.is_expired
   OR t.from_hospital_id = t.to_hospital_id
   OR t.usable_qty_before_expiry <= 0
   OR t.usable_qty_before_expiry > t.qty_on_hand
   OR s.is_cold_chain
