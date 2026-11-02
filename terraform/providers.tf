# Two connections, one per job, so each resource runs with the smallest role that can do it:
# SYSADMIN owns the warehouse, database and schemas; SECURITYADMIN owns roles and grants.
provider "snowflake" {
  organization_name = var.snowflake_organization
  account_name      = var.snowflake_account
  user              = var.snowflake_user
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(var.snowflake_private_key_path)
  role              = "SYSADMIN"
}

provider "snowflake" {
  alias             = "security"
  organization_name = var.snowflake_organization
  account_name      = var.snowflake_account
  user              = var.snowflake_user
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(var.snowflake_private_key_path)
  role              = "SECURITYADMIN"
}
