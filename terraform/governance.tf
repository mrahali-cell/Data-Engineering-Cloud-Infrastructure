# Who can see what in GOLD, enforced by Snowflake itself (not by the dashboard).
#
#   Role                         Rows                         Purchase price (unit_cost_eur)
#   MEDIRELAIS_PIPELINE          all (it builds the tables)   visible
#   MEDIRELAIS_FINANCE           all                          visible
#   MEDIRELAIS_READER            all (network dashboard)      hidden
#   MEDIRELAIS_PHARMACIST_Hxx    its own hospital only        hidden
#   SYSADMIN / ACCOUNTADMIN      all (platform admins)        hidden
#
# The rules live here; dbt only attaches them to the gold tables after each rebuild
# (dbt_project.yml post-hooks), so the pipeline applies the rules but cannot rewrite them.
# Checks use CURRENT_ROLE(), not IS_ROLE_IN_SESSION(): Snowsight turns on all secondary roles
# by default, which would let an admin testing as a pharmacist still see every hospital.

resource "snowflake_schema" "governance" {
  database            = snowflake_database.medirelais.name
  name                = "GOVERNANCE"
  is_transient        = false
  with_managed_access = false
  comment             = "Access rules: who sees which rows and columns"
}

locals {
  # Which pharmacist role sees which hospital. Adding a hospital = one line here + a role in roles.tf.
  hospital_access = {
    MEDIRELAIS_PHARMACIST_H01 = "H01"
    MEDIRELAIS_PHARMACIST_H04 = "H04"
  }
  see_all_rows   = ["MEDIRELAIS_PIPELINE", "MEDIRELAIS_FINANCE", "MEDIRELAIS_READER", "SYSADMIN", "ACCOUNTADMIN"]
  see_prices     = ["MEDIRELAIS_PIPELINE", "MEDIRELAIS_FINANCE"]
  governance_fqn = "${snowflake_database.medirelais.name}.${snowflake_schema.governance.name}"
  role_list      = { rows = join(", ", [for r in local.see_all_rows : "'${r}'"]), prices = join(", ", [for r in local.see_prices : "'${r}'"]) }
}

# The mapping table, rebuilt from the map above whenever it changes
resource "snowflake_execute" "hospital_access" {
  execute = <<-SQL
    CREATE OR REPLACE TABLE ${local.governance_fqn}.HOSPITAL_ACCESS
      COMMENT = 'Managed by Terraform (governance.tf): which role sees which hospital'
    AS SELECT column1::VARCHAR AS role_name, column2::VARCHAR AS hospital_id
    FROM VALUES ${join(", ", [for role, h in local.hospital_access : "('${role}', '${h}')"])}
  SQL
  revert  = "DROP TABLE IF EXISTS ${local.governance_fqn}.HOSPITAL_ACCESS"
}

# One hospital column: value at risk, days of cover
resource "snowflake_row_access_policy" "hospital_rows" {
  name     = "HOSPITAL_ROWS"
  database = snowflake_database.medirelais.name
  schema   = snowflake_schema.governance.name
  argument {
    name = "ROW_HOSPITAL_ID"
    type = "VARCHAR"
  }
  body    = <<-SQL
    CURRENT_ROLE() IN (${local.role_list.rows})
    OR EXISTS (SELECT 1 FROM ${local.governance_fqn}.HOSPITAL_ACCESS a
               WHERE a.role_name = CURRENT_ROLE() AND a.hospital_id = ROW_HOSPITAL_ID)
  SQL
  comment = "Pharmacists see their own hospital only"

  depends_on = [snowflake_execute.hospital_access]
}

# Transfers involve two hospitals: a pharmacist sees what its hospital sends or receives
resource "snowflake_row_access_policy" "transfer_rows" {
  name     = "TRANSFER_ROWS"
  database = snowflake_database.medirelais.name
  schema   = snowflake_schema.governance.name
  argument {
    name = "FROM_HOSPITAL"
    type = "VARCHAR"
  }
  argument {
    name = "TO_HOSPITAL"
    type = "VARCHAR"
  }
  body    = <<-SQL
    CURRENT_ROLE() IN (${local.role_list.rows})
    OR EXISTS (SELECT 1 FROM ${local.governance_fqn}.HOSPITAL_ACCESS a
               WHERE a.role_name = CURRENT_ROLE() AND a.hospital_id IN (FROM_HOSPITAL, TO_HOSPITAL))
  SQL
  comment = "Pharmacists see the transfers their hospital sends or receives"

  depends_on = [snowflake_execute.hospital_access]
}

# Negotiated purchase prices: finance and the pipeline only
resource "snowflake_masking_policy" "purchase_price" {
  name             = "PURCHASE_PRICE"
  database         = snowflake_database.medirelais.name
  schema           = snowflake_schema.governance.name
  return_data_type = "NUMBER"
  argument {
    name = "PRICE"
    type = "NUMBER"
  }
  body    = <<-SQL
    CASE WHEN CURRENT_ROLE() IN (${local.role_list.prices}) THEN PRICE ELSE NULL END
  SQL
  comment = "Negotiated purchase prices: finance and the pipeline only"
}

# The pipeline (dbt) may attach these policies to the tables it builds, nothing more
resource "snowflake_grant_privileges_to_account_role" "pipeline_governance_schema" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.pipeline.name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.governance.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "pipeline_apply_row_policies" {
  provider          = snowflake.security
  for_each          = { hospital = snowflake_row_access_policy.hospital_rows, transfer = snowflake_row_access_policy.transfer_rows }
  account_role_name = snowflake_account_role.pipeline.name
  privileges        = ["APPLY"]
  on_schema_object {
    object_type = "ROW ACCESS POLICY"
    object_name = each.value.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "pipeline_apply_masking" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.pipeline.name
  privileges        = ["APPLY"]
  on_schema_object {
    object_type = "MASKING POLICY"
    object_name = snowflake_masking_policy.purchase_price.fully_qualified_name
  }
}

# Dashboards: a Streamlit app runs with its owner's rights, and Snowflake cannot transfer the
# ownership of an app, so each app is created by the role whose view it must show:
#   - READER creates the network dashboard (03_schedule.sql): every hospital, no purchase prices;
#   - each pharmacist role creates its hospital's app (06_hospital_apps.sql): its own hospital only.
# These owners may create apps in GOLD and read the Git repo, nothing more.
# The pipeline inherits READER so that whoever runs 03_schedule.sql can switch to it.
locals {
  dashboard_owners = toset(concat(["MEDIRELAIS_READER"], keys(local.hospital_access)))
}

resource "snowflake_grant_account_role" "reader_to_pipeline" {
  provider         = snowflake.security
  role_name        = snowflake_account_role.reader["MEDIRELAIS_READER"].name
  parent_role_name = snowflake_account_role.pipeline.name
}

resource "snowflake_grant_privileges_to_account_role" "reader_create_dashboard" {
  provider          = snowflake.security
  for_each          = local.dashboard_owners
  account_role_name = snowflake_account_role.reader[each.value].name
  privileges        = ["CREATE STREAMLIT"]
  on_schema {
    schema_name = snowflake_schema.layer["GOLD"].fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_public_schema" {
  provider          = snowflake.security
  for_each          = local.dashboard_owners
  account_role_name = snowflake_account_role.reader[each.value].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "\"${snowflake_database.medirelais.name}\".\"PUBLIC\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_git_repo" {
  provider          = snowflake.security
  for_each          = local.dashboard_owners
  account_role_name = snowflake_account_role.reader[each.value].name
  privileges        = ["READ"]
  on_schema_object {
    object_type = "GIT REPOSITORY"
    object_name = "\"${snowflake_database.medirelais.name}\".\"PUBLIC\".\"MEDIRELAIS_REPO\""
  }
}

# The READER grants existed before the for_each: keep them in place instead of revoking them
moved {
  from = snowflake_grant_privileges_to_account_role.reader_create_dashboard
  to   = snowflake_grant_privileges_to_account_role.reader_create_dashboard["MEDIRELAIS_READER"]
}

moved {
  from = snowflake_grant_privileges_to_account_role.reader_public_schema
  to   = snowflake_grant_privileges_to_account_role.reader_public_schema["MEDIRELAIS_READER"]
}

moved {
  from = snowflake_grant_privileges_to_account_role.reader_git_repo
  to   = snowflake_grant_privileges_to_account_role.reader_git_repo["MEDIRELAIS_READER"]
}
