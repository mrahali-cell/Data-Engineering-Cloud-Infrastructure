-- README: "Priority: medicines in national shortage first, then the largest saveable value".
-- The test FAILS with one row per pair of transfers in the wrong order.
SELECT a.snapshot_date,
       a.batch_id AS ranked_first, a.priority_rank AS rank_first,
       b.batch_id AS ranked_after, b.priority_rank AS rank_after
FROM {{ ref('gold_transfer_suggestions') }} a
JOIN {{ ref('gold_transfer_suggestions') }} b
  ON a.snapshot_date = b.snapshot_date
 AND a.priority_rank < b.priority_rank
WHERE (NOT a.is_national_shortage AND b.is_national_shortage)                -- shortage ranked after a non-shortage
   OR (a.is_national_shortage = b.is_national_shortage
       AND a.saveable_value_eur < b.saveable_value_eur)                      -- smaller value ranked first
