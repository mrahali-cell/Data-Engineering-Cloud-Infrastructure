-- MédiRelais · Step 6: one hospital dashboard per pharmacist role.
-- Same code (streamlit_hospital/), one app per hospital. Each app is created BY that hospital's
-- pharmacist role, so it runs with that role's rights: the row access policy shows its own
-- hospital only, and the masking policy hides purchase prices (terraform/governance.tf).
-- Re-run after each merge that changes streamlit_hospital/ (after 03_schedule.sql step 1).

USE WAREHOUSE MEDIRELAIS_WH;

USE ROLE MEDIRELAIS_PHARMACIST_H01;
CREATE OR REPLACE STREAMLIT MEDIRELAIS.GOLD.HOSPITAL_DASHBOARD_H01
  FROM '@MEDIRELAIS.PUBLIC.MEDIRELAIS_REPO/branches/main/streamlit_hospital'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = MEDIRELAIS_WH
  RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
  TITLE = 'MediRelais - H01';

USE ROLE MEDIRELAIS_PHARMACIST_H04;
CREATE OR REPLACE STREAMLIT MEDIRELAIS.GOLD.HOSPITAL_DASHBOARD_H04
  FROM '@MEDIRELAIS.PUBLIC.MEDIRELAIS_REPO/branches/main/streamlit_hospital'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = MEDIRELAIS_WH
  RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
  TITLE = 'MediRelais - H04';

USE ROLE MEDIRELAIS_PIPELINE;
