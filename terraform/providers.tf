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

# AWS: credentials come from the environment (AWS_PROFILE), never from the code.
# eu-north-1 is the only region the account's guardrail policy allows.
provider "aws" {
  region = "eu-north-1"

  default_tags {
    tags = {
      project    = "medirelais"
      managed_by = "terraform"
    }
  }
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
