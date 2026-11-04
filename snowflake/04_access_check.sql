-- MédiRelais · Step 4: check who can see what (rules in terraform/governance.tf)
-- Run statement by statement (Ctrl+Enter on each block) and compare the results.
-- Secondary roles are switched off first: otherwise your admin roles stay active in the
-- background and every check below would show everything.
USE SECONDARY ROLES NONE;
USE WAREHOUSE MEDIRELAIS_WH;

-- 1. Pharmacist of H01: only H01's batches, purchase price hidden (NULL)
USE ROLE MEDIRELAIS_PHARMACIST_H01;
SELECT hospital_id, product_name, qty_on_hand, unit_cost_eur, value_at_risk_eur, transfer_block_reason
FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
ORDER BY value_at_risk_eur DESC;

-- 2. Pharmacist of H04: the same query returns H04's rows only, and only the transfers
--    H04 sends or receives
USE ROLE MEDIRELAIS_PHARMACIST_H04;
SELECT hospital_id, product_name, qty_on_hand, unit_cost_eur, value_at_risk_eur, transfer_block_reason
FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
ORDER BY value_at_risk_eur DESC;

SELECT from_hospital, to_hospital, product_name, saveable_value_eur
FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS;

-- 3. Reader (the network dashboard): every hospital, purchase price still hidden
USE ROLE MEDIRELAIS_READER;
SELECT hospital_id, product_name, qty_on_hand, unit_cost_eur, value_at_risk_eur, transfer_block_reason
FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
ORDER BY value_at_risk_eur DESC;

-- 4. Finance: every hospital, purchase price visible
USE ROLE MEDIRELAIS_FINANCE;
SELECT hospital_id, product_name, qty_on_hand, unit_cost_eur, value_at_risk_eur, transfer_block_reason
FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
ORDER BY value_at_risk_eur DESC;

-- 5. Reader on raw data: refused ("does not exist or not authorized"), GOLD only
USE ROLE MEDIRELAIS_READER;
SELECT COUNT(*) FROM MEDIRELAIS.BRONZE.STOCK_RAW;

-- 6. Audit: who read the gold tables in the last 7 days, with which role
--    (needs ACCOUNTADMIN; Snowflake fills these views with up to 3 hours of delay)
USE ROLE ACCOUNTADMIN;
SELECT a.query_start_time,
       a.user_name,
       q.role_name,
       obj.value:"objectName"::STRING AS table_read
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY a
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q ON q.query_id = a.query_id,
     LATERAL FLATTEN(input => a.base_objects_accessed) obj
WHERE obj.value:"objectName"::STRING LIKE 'MEDIRELAIS.GOLD.%'
  AND a.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
ORDER BY a.query_start_time DESC;

-- 7. Grants view: who holds which role, and why (needs ACCOUNTADMIN; same 3-hour delay)
--    Expected: ACCOUNTADMIN for two people only, service users (TERRAFORM, the pipeline) on
--    their own roles, and no one on ACCOUNTADMIN for daily work.
SELECT g.grantee_name AS user_name,
       u.type         AS user_type,                -- PERSON or SERVICE (key pair only)
       g.role,
       g.granted_by,
       g.created_on
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS g
JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u ON u.name = g.grantee_name AND u.deleted_on IS NULL
WHERE g.deleted_on IS NULL
ORDER BY g.role, g.grantee_name;

-- 8. What each MédiRelais role may do, and what it owns (the role hierarchy shows as
--    USAGE on ROLE: e.g. MEDIRELAIS_PIPELINE -> SYSADMIN)
SELECT grantee_name AS role, privilege, granted_on, name AS object_name, granted_by
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE deleted_on IS NULL
  AND (grantee_name LIKE 'MEDIRELAIS_%' OR (granted_on = 'ROLE' AND name LIKE 'MEDIRELAIS_%'))
ORDER BY grantee_name, privilege = 'OWNERSHIP' DESC, granted_on, object_name;

-- 9. Who logged in over the last 7 days, how, and from where
SELECT event_timestamp, user_name, first_authentication_factor, second_authentication_factor,
       client_ip, reported_client_type, is_success, error_message
FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE event_timestamp >= DATEADD(day, -7, CURRENT_TIMESTAMP())
ORDER BY event_timestamp DESC;

-- 10. Classification (tags in terraform/tags.tf, set on silver and gold by dbt): every column
--     of a gold table with its tags, live (no delay)
SELECT column_name, tag_name, tag_value, level
FROM TABLE(MEDIRELAIS.INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS(
       'MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK', 'table'))
ORDER BY column_name, tag_name;

-- 11. Tag coverage: share of MédiRelais tables that carry each tag (up to 2 hours of delay)
WITH tables AS (
    SELECT table_schema, table_name
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
    WHERE table_catalog = 'MEDIRELAIS' AND deleted IS NULL
      AND table_schema IN ('BRONZE', 'SILVER', 'GOLD')
),
tagged AS (
    SELECT object_schema, object_name, tag_name, tag_value
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
    WHERE object_database = 'MEDIRELAIS' AND domain = 'TABLE' AND object_deleted IS NULL
)
SELECT g.tag_name,
       COUNT(DISTINCT g.object_schema || '.' || g.object_name)       AS tables_tagged,
       (SELECT COUNT(*) FROM tables)                                  AS tables_total,
       ROUND(100 * tables_tagged / NULLIF(tables_total, 0), 0)        AS coverage_pct
FROM tagged g
JOIN tables t ON t.table_schema = g.object_schema AND t.table_name = g.object_name
GROUP BY g.tag_name
ORDER BY g.tag_name;
