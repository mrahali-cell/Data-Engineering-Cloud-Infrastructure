-- USE CASE 1 - the action: for each transferable batch, the hospital that can use the most
-- of it before it expires, and how much of its value that saves.
-- Receivers come from consumption, so a hospital that has run out still counts.
-- Cold-chain medicines never get here: gold_value_at_risk marks them not transferable.
-- Assumption: every hospital uses its soonest-expiring stock first. So a candidate first uses
-- its own stock that expires before (or with) the batch; what it can still use before the
-- batch expires is daily use x days left, minus that stock. That is the usable quantity.
-- The receiver is the candidate with the largest usable quantity (then the highest daily use,
-- then hospital_id, so the same data always gives the same answer). A batch that no other
-- hospital can use before it expires gets no suggestion: moving it would save nothing.
-- Several batches can go to the same receiver: can_use_before_expiry checks them together.
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
-- For each batch and each other hospital: its own stock of the product that expires
-- before (or with) the batch, which it will use first
own_stock_ahead AS (
    SELECT r.snapshot_date, r.batch_id, s.hospital_id, SUM(s.qty_on_hand) AS qty_ahead
    FROM at_risk r
    JOIN {{ ref('silver_stock') }} s
      ON s.snapshot_date = r.snapshot_date
     AND s.product_id    = r.product_id
     AND s.hospital_id  <> r.hospital_id
     AND NOT s.is_expired
     AND s.expiry_date  <= r.expiry_date
    GROUP BY r.snapshot_date, r.batch_id, s.hospital_id
),
-- Every other hospital that uses the product, with what it could use of this batch in time
candidates AS (
    SELECT
        r.snapshot_date,
        r.batch_id,
        u.hospital_id,
        u.hospital_name,
        u.avg_daily_use,
        COALESCE(own.qty_ahead, 0)                                   AS own_stock_used_first,
        LEAST(r.qty_on_hand,
              GREATEST(0, FLOOR(u.avg_daily_use * r.days_to_expiry) - COALESCE(own.qty_ahead, 0))
        )                                                            AS usable_qty
    FROM at_risk r
    JOIN usage u
      ON u.snapshot_date = r.snapshot_date
     AND u.product_id    = r.product_id
     AND u.hospital_id  <> r.hospital_id
    LEFT JOIN own_stock_ahead own
      ON own.snapshot_date = r.snapshot_date
     AND own.batch_id      = r.batch_id
     AND own.hospital_id   = u.hospital_id
),
best_receiver AS (
    SELECT
        r.*,
        c.hospital_id          AS to_hospital_id,
        c.hospital_name        AS to_hospital_name,
        c.avg_daily_use        AS to_hospital_daily_use,
        c.own_stock_used_first AS to_hospital_stock_used_first,
        c.usable_qty
    FROM at_risk r
    JOIN candidates c
      ON c.snapshot_date = r.snapshot_date
     AND c.batch_id      = r.batch_id
    WHERE c.usable_qty > 0
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY r.snapshot_date, r.batch_id
        ORDER BY c.usable_qty DESC, c.avg_daily_use DESC, c.hospital_id
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
    b.to_hospital_stock_used_first,
    b.usable_qty                                            AS usable_qty_before_expiry,
    ROUND(b.usable_qty / b.qty_on_hand, 2)                  AS share_usable_before_expiry,
    ROUND(b.usable_qty * b.unit_cost_eur, 2)                AS saveable_value_eur,
    q.qty_queued_up_to_this_batch,
    ROUND(q.qty_queued_up_to_this_batch / b.to_hospital_daily_use, 0) AS days_to_use_it_all,
    q.qty_queued_up_to_this_batch / b.to_hospital_daily_use <= b.days_to_expiry AS can_use_before_expiry,
    b.is_national_shortage,
    b.shortage_status,
    -- handle first: medicines short in France, then the transfers that save the most
    ROW_NUMBER() OVER (PARTITION BY b.snapshot_date
                       ORDER BY b.is_national_shortage DESC,
                                ROUND(b.usable_qty * b.unit_cost_eur, 2) DESC,
                                b.batch_id) AS priority_rank
FROM best_receiver b
JOIN queued q
  ON q.snapshot_date = b.snapshot_date
 AND q.hospital_id   = b.to_hospital_id
 AND q.batch_id      = b.batch_id
