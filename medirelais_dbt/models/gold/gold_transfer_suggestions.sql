-- USE CASE 1 - the action: for each transferable batch, the hospital that
-- uses the most of this product, and whether it can use it before it expires.
-- Receivers come from consumption, so a hospital that has run out still counts.
-- Ties are broken by hospital_id: the same data always gives the same answer.
-- Several batches can go to the same receiver. Assumption: the receiver uses its
-- soonest-expiring stock first (its own and the incoming batches), so a batch is
-- usable in time only if everything queued before it, plus itself, is used first.
WITH at_risk AS (
    SELECT * FROM {{ ref('gold_value_at_risk') }}
    WHERE is_transferable
),
usage AS (
    SELECT u.snapshot_date, u.hospital_id, h.hospital_name, u.product_id, u.avg_daily_use
    FROM {{ ref('silver_daily_use') }} u
    JOIN {{ ref('silver_hospitals') }} h ON u.hospital_id = h.hospital_id
    WHERE u.avg_daily_use > 0
),
best_receiver AS (
    SELECT
        r.*,
        u.hospital_id   AS to_hospital_id,
        u.hospital_name AS to_hospital_name,
        u.avg_daily_use AS to_hospital_daily_use
    FROM at_risk r
    JOIN usage u
      ON r.snapshot_date = u.snapshot_date
     AND r.product_id    = u.product_id
     AND r.hospital_id  <> u.hospital_id
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY r.snapshot_date, r.batch_id
        ORDER BY u.avg_daily_use DESC, u.hospital_id
    ) = 1
),
-- What each receiver will have to get through: the incoming batches plus its own
-- stock (minus any of its own batches that are being sent away)
queue AS (
    SELECT snapshot_date, to_hospital_id AS hospital_id, product_id, batch_id, qty_on_hand, expiry_date
    FROM best_receiver
    UNION ALL
    SELECT s.snapshot_date, s.hospital_id, s.product_id, s.batch_id, s.qty_on_hand, s.expiry_date
    FROM {{ ref('silver_stock') }} s
    LEFT JOIN best_receiver b
      ON s.snapshot_date = b.snapshot_date
     AND s.batch_id      = b.batch_id
    WHERE NOT s.is_expired
      AND b.batch_id IS NULL
),
queued AS (
    SELECT
        snapshot_date,
        hospital_id,
        batch_id,
        SUM(qty_on_hand) OVER (
            PARTITION BY snapshot_date, hospital_id, product_id
            ORDER BY expiry_date, batch_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS qty_queued_up_to_this_batch
    FROM queue
)
SELECT
    b.snapshot_date,
    b.batch_id,
    b.product_id,
    b.product_name,
    b.hospital_id                                           AS from_hospital_id,
    b.hospital_name                                         AS from_hospital,
    b.to_hospital_id,
    b.to_hospital_name                                      AS to_hospital,
    b.qty_on_hand,
    b.value_at_risk_eur,
    b.days_to_expiry,
    ROUND(b.to_hospital_daily_use, 1)                       AS to_hospital_daily_use,
    q.qty_queued_up_to_this_batch,
    ROUND(q.qty_queued_up_to_this_batch / b.to_hospital_daily_use, 0) AS days_to_use_it_all,
    q.qty_queued_up_to_this_batch / b.to_hospital_daily_use <= b.days_to_expiry AS can_use_before_expiry
FROM best_receiver b
JOIN queued q
  ON q.snapshot_date = b.snapshot_date
 AND q.hospital_id   = b.to_hospital_id
 AND q.batch_id      = b.batch_id
