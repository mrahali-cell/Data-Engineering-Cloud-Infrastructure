-- MédiRelais · Step 3: deploy the dbt project from GitHub and run it every day at 06:00
-- Re-run this script to deploy a new version of the dbt code from the main branch.
USE ROLE MEDIRELAIS_PIPELINE;
USE WAREHOUSE MEDIRELAIS_WH;

-- 1. Link Snowflake to the GitHub repo and pull the latest commits
CREATE GIT REPOSITORY IF NOT EXISTS MEDIRELAIS.PUBLIC.MEDIRELAIS_REPO
  API_INTEGRATION = MEDIRELAIS_GITHUB
  ORIGIN = 'https://github.com/mrahali-cell/Data-Engineering-Cloud-Infrastructure.git';
ALTER GIT REPOSITORY MEDIRELAIS.PUBLIC.MEDIRELAIS_REPO FETCH;

-- 2. Deploy the dbt project from the main branch (not from a personal workspace)
CREATE OR REPLACE DBT PROJECT MEDIRELAIS.PUBLIC.MEDIRELAIS_DBT
  FROM '@MEDIRELAIS.PUBLIC.MEDIRELAIS_REPO/branches/main/medirelais_dbt'
  DBT_VERSION = '1.9.4';

-- 3. Run the whole pipeline (silver + gold + tests) every day at 06:00 Paris time
CREATE OR REPLACE TASK MEDIRELAIS.PUBLIC.DAILY_PIPELINE
  WAREHOUSE = MEDIRELAIS_WH
  SCHEDULE = 'USING CRON 0 6 * * * Europe/Paris'
AS
  EXECUTE DBT PROJECT MEDIRELAIS.PUBLIC.MEDIRELAIS_DBT ARGS = 'build';

-- 4. Turn the schedule on, and run it once now to test
ALTER TASK MEDIRELAIS.PUBLIC.DAILY_PIPELINE RESUME;
EXECUTE TASK MEDIRELAIS.PUBLIC.DAILY_PIPELINE;

-- 5. Check the runs (expected: SUCCEEDED)
SELECT name, state, scheduled_time, completed_time, error_message
FROM TABLE(MEDIRELAIS.INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => 'DAILY_PIPELINE'))
ORDER BY scheduled_time DESC
LIMIT 5;
