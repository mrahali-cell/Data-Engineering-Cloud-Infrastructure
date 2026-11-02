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
