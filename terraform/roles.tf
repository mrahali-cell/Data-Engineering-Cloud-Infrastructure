# Governance roles: who can read what. Each one reads the GOLD layer only, through the
# project warehouse. Row access and masking policies (governance step) then decide which
# rows and columns each of them sees.
locals {
  readers = {
    MEDIRELAIS_READER         = "Reads GOLD only; the role behind the dashboard"
    MEDIRELAIS_FINANCE        = "Reads GOLD including purchase prices (unit costs)"
    MEDIRELAIS_PHARMACIST_H01 = "Pharmacist of hospital H01: sees H01 rows only"
    MEDIRELAIS_PHARMACIST_H04 = "Pharmacist of hospital H04: sees H04 rows only"
  }
}

resource "snowflake_account_role" "reader" {
  provider = snowflake.security
  for_each = local.readers
  name     = each.key
  comment  = each.value
}

# Role hierarchy: every custom role rolls up to SYSADMIN (Snowflake best practice)
resource "snowflake_grant_account_role" "reader_to_sysadmin" {
  provider         = snowflake.security
  for_each         = snowflake_account_role.reader
  role_name        = each.value.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_privileges_to_account_role" "reader_warehouse" {
  provider          = snowflake.security
  for_each          = snowflake_account_role.reader
  account_role_name = each.value.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.medirelais.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_database" {
  provider          = snowflake.security
  for_each          = snowflake_account_role.reader
  account_role_name = each.value.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.medirelais.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_gold_schema" {
  provider          = snowflake.security
  for_each          = snowflake_account_role.reader
  account_role_name = each.value.name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.layer["GOLD"].fully_qualified_name
  }
}

# The gold tables that exist today...
resource "snowflake_grant_privileges_to_account_role" "reader_gold_tables" {
  provider          = snowflake.security
  for_each          = snowflake_account_role.reader
  account_role_name = each.value.name
  privileges        = ["SELECT"]
  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.layer["GOLD"].fully_qualified_name
    }
  }
}

# ...and the ones dbt recreates on every run
resource "snowflake_grant_privileges_to_account_role" "reader_gold_future_tables" {
  provider          = snowflake.security
  for_each          = snowflake_account_role.reader
  account_role_name = each.value.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.layer["GOLD"].fully_qualified_name
    }
  }
}
