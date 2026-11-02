-- MédiRelais · Terraform bootstrap (manual step, run once by an admin in Snowsight, as ACCOUNTADMIN)
-- Creates the service user Terraform logs in with. Key-pair only: no password exists.
-- 1. Generate the key pair (private key stays in terraform/keys/, ignored by git):
--      openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -out terraform/keys/terraform_rsa_key.p8
--      openssl rsa -in terraform/keys/terraform_rsa_key.p8 -pubout -out terraform/keys/terraform_rsa_key.pub
-- 2. Paste the public key below (the lines between BEGIN and END, joined into one line).
-- 3. Pick a warehouse for the worksheet (a scripting block needs one), then run it. It is one single
--    statement, so the Run button executes all of it wherever the cursor is.
--
-- Least privilege for Terraform: SYSADMIN creates objects, SECURITYADMIN creates roles and grants.
-- No ACCOUNTADMIN.
EXECUTE IMMEDIATE $$
BEGIN
  CREATE USER IF NOT EXISTS TERRAFORM
    TYPE = SERVICE
    DEFAULT_ROLE = SYSADMIN
    RSA_PUBLIC_KEY = '<paste the public key here>'
    COMMENT = 'Terraform (infrastructure as code for MediRelais), key-pair login only';
  GRANT ROLE SYSADMIN      TO USER TERRAFORM;
  GRANT ROLE SECURITYADMIN TO USER TERRAFORM;
  RETURN 'TERRAFORM user created with SYSADMIN and SECURITYADMIN';
END;
$$;

-- Check: type = SERVICE, has_rsa_public_key = true
SHOW USERS LIKE 'TERRAFORM';

-- Archive step (archive.tf): SYSADMIN may create storage integrations.
-- Only ACCOUNTADMIN can grant this account-level privilege, so it stays a manual step.
GRANT CREATE INTEGRATION ON ACCOUNT TO ROLE SYSADMIN;
