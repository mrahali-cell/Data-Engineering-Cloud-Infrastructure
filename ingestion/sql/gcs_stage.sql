-- MédiRelais · OPTIONAL: use a Google Cloud Storage bucket as the landing zone for S2 (cloud provider in the architecture)
-- Run once as ACCOUNTADMIN, after the bucket exists (created by Terraform, or by hand in the GCP console).
-- Replace medirelais-landing with your bucket name.

CREATE STORAGE INTEGRATION IF NOT EXISTS MEDIRELAIS_GCS_INT
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'GCS'
  ENABLED = TRUE
  STORAGE_ALLOWED_LOCATIONS = ('gcs://medirelais-landing/');

-- Gives the Google service account Snowflake will use: copy STORAGE_GCP_SERVICE_ACCOUNT,
-- then in GCP: bucket -> Permissions -> Grant access -> that account -> role "Storage Object Viewer".
DESC STORAGE INTEGRATION MEDIRELAIS_GCS_INT;

CREATE STAGE IF NOT EXISTS MEDIRELAIS.BRONZE.GCS_STAGE
  URL = 'gcs://medirelais-landing/'
  STORAGE_INTEGRATION = MEDIRELAIS_GCS_INT;

-- Check: should list the files uploaded by ingest_consumption_files.py (GCS_BUCKET set in .env)
LIST @MEDIRELAIS.BRONZE.GCS_STAGE/consumption/;
