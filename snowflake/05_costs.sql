-- MédiRelais · Step 5: what the platform costs, who spends it, and the cap on it
-- Run block by block (Ctrl+Enter). Needs ACCOUNTADMIN: the usage views live in the SNOWFLAKE
-- database, and Snowflake fills them with up to 3 hours of delay.
USE ROLE ACCOUNTADMIN;
USE SECONDARY ROLES NONE;
USE WAREHOUSE MEDIRELAIS_WH;

-- Prices used to turn credits into euros. Check them before quoting a number:
-- price per credit in Admin » Billing, storage price on snowflake.com/pricing.
SET credit_usd = 3.90;          -- Enterprise edition, AWS Paris, on demand
SET storage_usd_per_tb = 23;    -- per TB per month, compressed
SET usd_eur = 0.86;             -- exchange rate of the day

-- 1. Visibility: credits and euros per day and per service, last 30 days.
--    WAREHOUSE_METERING = queries (dbt, dashboard, ingestion); CLOUD_SERVICES is free up to
--    10% of the warehouse credits, so credits_billed is what we actually pay.
SELECT usage_date,
       service_type,
       ROUND(SUM(credits_billed), 3)                              AS credits,
       ROUND(SUM(credits_billed) * $credit_usd * $usd_eur, 2)     AS cost_eur
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
WHERE usage_date >= DATEADD(day, -30, CURRENT_DATE())
GROUP BY usage_date, service_type
ORDER BY usage_date DESC, credits DESC;

-- 2. Showback: who spent the warehouse credits, by role (= team) and query tag, last 30 days.
--    "idle" is the time the warehouse ran with no query: paid, but nobody used it.
WITH by_role AS (
    SELECT COALESCE(q.role_name, 'unknown')        AS role_name,
           COALESCE(NULLIF(a.query_tag, ''), '-')  AS query_tag,
           SUM(a.credits_attributed_compute)       AS credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY a
    LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q ON q.query_id = a.query_id
    WHERE a.warehouse_name = 'MEDIRELAIS_WH'
      AND a.start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
    GROUP BY 1, 2
),
metered AS (
    SELECT SUM(credits_used_compute) AS credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE warehouse_name = 'MEDIRELAIS_WH'
      AND start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
)
SELECT role_name, query_tag,
       ROUND(credits, 3)                                  AS credits,
       ROUND(credits * $credit_usd * $usd_eur, 2)         AS cost_eur,
       ROUND(100 * credits / (SELECT credits FROM metered), 1) AS pct_of_warehouse
FROM (
    SELECT * FROM by_role
    UNION ALL
    SELECT 'idle (no query running)', '-', (SELECT credits FROM metered) - (SELECT SUM(credits) FROM by_role)
)
ORDER BY credits DESC;

-- 3. Cost of one run of the daily pipeline (task DAILY_PIPELINE = dbt build), last 30 days.
--    What the warehouse billed in the hour of the run: it includes the 60 s minimum after each
--    resume and the 60 s auto-suspend tail, which per-query attribution leaves out.
SELECT t.scheduled_time,
       t.state,
       DATEDIFF(second, t.query_start_time, t.completed_time)  AS duration_s,
       ROUND(w.credits_used, 4)                                AS credits_billed_that_hour,
       ROUND(w.credits_used * $credit_usd * $usd_eur, 3)       AS cost_eur
FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY t
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY w
       ON w.warehouse_name = 'MEDIRELAIS_WH'
      AND w.start_time = DATE_TRUNC(hour, t.query_start_time)
WHERE t.name = 'DAILY_PIPELINE'
  AND t.scheduled_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
ORDER BY t.scheduled_time DESC;

-- 4. Storage: what each database keeps, including Fail-safe (7 days Snowflake keeps after a drop)
SELECT database_name,
       ROUND(average_database_bytes / POWER(1024, 3), 3)  AS data_gb,
       ROUND(average_failsafe_bytes / POWER(1024, 3), 3)  AS failsafe_gb,
       ROUND((average_database_bytes + average_failsafe_bytes) / POWER(1024, 4)
             * $storage_usd_per_tb * $usd_eur, 4)          AS cost_eur_per_month
FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY
WHERE usage_date = (SELECT MAX(usage_date) FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY)
  AND deleted IS NULL
ORDER BY data_gb DESC;

-- 5. Data transfer: bytes that left Snowflake's region (the nightly archive goes from
--    Paris to the S3 bucket in Stockholm, which is billed per TB)
SELECT DATE_TRUNC(day, start_time)          AS day,
       target_cloud, target_region, transfer_type,
       ROUND(SUM(bytes_transferred) / POWER(1024, 2), 3) AS mb
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_TRANSFER_HISTORY
WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2, 3, 4
ORDER BY day DESC;

-- 6. Business ratio: what one month of platform costs, against the medicine value the
--    suggested transfers can save on the latest day
WITH month_cost AS (
    SELECT SUM(credits_billed) * $credit_usd * $usd_eur AS eur
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
    WHERE usage_date >= DATEADD(day, -30, CURRENT_DATE()) AND usage_date < CURRENT_DATE()
),
saved AS (
    SELECT SUM(saveable_value_eur) AS eur
    FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS
    WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS)
)
SELECT ROUND(month_cost.eur, 2)                 AS platform_cost_last_30_days_eur,
       ROUND(saved.eur, 0)                      AS saveable_value_latest_day_eur,
       ROUND(saved.eur / NULLIF(month_cost.eur, 0), 0) AS euros_saved_per_euro_spent
FROM month_cost, saved;

-- 7. Control: a monthly credit quota on the warehouse. Email to the account admins at 75%,
--    stop new queries at 90%, stop everything at 100%. Resets on the 1st of each month.
--    Run once (only ACCOUNTADMIN can create a resource monitor).
CREATE RESOURCE MONITOR IF NOT EXISTS MEDIRELAIS_MONITOR
  WITH CREDIT_QUOTA = 10
       FREQUENCY = MONTHLY
       START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 75 PERCENT DO NOTIFY
           ON 90 PERCENT DO SUSPEND
           ON 100 PERCENT DO SUSPEND_IMMEDIATE;
ALTER WAREHOUSE MEDIRELAIS_WH SET RESOURCE_MONITOR = MEDIRELAIS_MONITOR;

SHOW RESOURCE MONITORS LIKE 'MEDIRELAIS_MONITOR';

-- 8. Control: a budget on everything tagged COST_CENTER = 'medirelais' (terraform/costs.tf):
--    the warehouse, and the database's storage and serverless work. The resource monitor (7)
--    caps one warehouse and stops it; the budget watches all our spend, stops nothing, and
--    emails the cost owner when the month is projected to go over the limit.
--    The account is shared with other projects, so the budget follows our tag, not the account.
--    Run once as ACCOUNTADMIN. The address must be verified in the user's Snowsight profile.
USE ROLE ACCOUNTADMIN;
CREATE NOTIFICATION INTEGRATION IF NOT EXISTS MEDIRELAIS_BUDGET_EMAIL
  TYPE = EMAIL ENABLED = TRUE ALLOWED_RECIPIENTS = ('<cost owner email>');
CREATE SNOWFLAKE.CORE.BUDGET IF NOT EXISTS MEDIRELAIS.GOVERNANCE.MEDIRELAIS_BUDGET();
CALL MEDIRELAIS.GOVERNANCE.MEDIRELAIS_BUDGET!SET_SPENDING_LIMIT(12);
CALL MEDIRELAIS.GOVERNANCE.MEDIRELAIS_BUDGET!SET_RESOURCE_TAGS(
  [[(SELECT SYSTEM$REFERENCE('TAG', 'MEDIRELAIS.GOVERNANCE.COST_CENTER', 'SESSION', 'APPLYBUDGET')), 'medirelais']],
  'UNION');
GRANT USAGE ON INTEGRATION MEDIRELAIS_BUDGET_EMAIL TO APPLICATION SNOWFLAKE;  -- the budget app sends the email
CALL MEDIRELAIS.GOVERNANCE.MEDIRELAIS_BUDGET!SET_EMAIL_NOTIFICATIONS('MEDIRELAIS_BUDGET_EMAIL', '<cost owner email>');

-- Check: limit, spend so far this month, and what the budget covers
CALL MEDIRELAIS.GOVERNANCE.MEDIRELAIS_BUDGET!GET_SPENDING_LIMIT();
CALL MEDIRELAIS.GOVERNANCE.MEDIRELAIS_BUDGET!GET_SPENDING_HISTORY();
CALL MEDIRELAIS.GOVERNANCE.MEDIRELAIS_BUDGET!GET_LINKED_RESOURCES();
