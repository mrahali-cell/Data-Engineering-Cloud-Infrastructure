-- MédiRelais · Step 3: deploy the dbt project and run it every day at 06:00
USE ROLE ACCOUNTADMIN;
USE WAREHOUSE MEDIRELAIS_WH;

-- 1. Deploy the dbt project inside Snowflake
CREATE OR REPLACE DBT PROJECT MEDIRELAIS.PUBLIC.MEDIRELAIS_DBT
  FROM $$snow://workspace/"USER$mrahali".PUBLIC.DEFAULT$/versions/live/medirelais_dbt$$
  DBT_VERSION = '1.9.4';

-- 2. Run the whole pipeline (silver + gold + tests) every day at 06:00 Paris time
CREATE OR REPLACE TASK MEDIRELAIS.PUBLIC.DAILY_PIPELINE
  WAREHOUSE = MEDIRELAIS_WH
  SCHEDULE = 'USING CRON 0 6 * * * Europe/Paris'
AS
  EXECUTE DBT PROJECT MEDIRELAIS.PUBLIC.MEDIRELAIS_DBT ARGS = 'build';

-- 3. Turn the schedule on, and run it once now to test
ALTER TASK MEDIRELAIS.PUBLIC.DAILY_PIPELINE RESUME;
EXECUTE TASK MEDIRELAIS.PUBLIC.DAILY_PIPELINE;

-- 4. Check the runs (expected: SUCCEEDED)
SELECT name, state, scheduled_time, completed_time, error_message
FROM TABLE(MEDIRELAIS.INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => 'DAILY_PIPELINE'))
ORDER BY scheduled_time DESC
LIMIT 5;
