# The long-lived platform objects. Tables are not here: dbt owns silver and gold,
# and the ingestion SQL owns bronze. The dbt project, the task and the dashboard are
# deployed by snowflake/03_schedule.sql.

# Values written as they are in Snowflake today, so the import changes nothing.
resource "snowflake_warehouse" "medirelais" {
  name                                = "MEDIRELAIS_WH"
  warehouse_type                      = "STANDARD"
  warehouse_size                      = "XSMALL"
  generation                          = "2"
  auto_suspend                        = 60 # seconds idle before it stops billing
  auto_resume                         = true
  min_cluster_count                   = 1
  max_cluster_count                   = 1
  scaling_policy                      = "STANDARD"
  enable_query_acceleration           = false # rents extra compute for big scans; our tables are small
  query_acceleration_max_scale_factor = 8
  # Monthly credit cap; the monitor itself needs ACCOUNTADMIN (snowflake/05_costs.sql, step 7)
  resource_monitor = "MEDIRELAIS_MONITOR"
}

resource "snowflake_database" "medirelais" {
  name = "MEDIRELAIS"

  lifecycle {
    prevent_destroy = true # a replace here would drop every table
  }
}

resource "snowflake_schema" "layer" {
  for_each = toset(["BRONZE", "SILVER", "GOLD"])
  database = snowflake_database.medirelais.name
  name     = each.key

  # Written explicitly: left unset, the provider plans to recreate the schema,
  # which would drop every table in it.
  is_transient        = false
  with_managed_access = false

  lifecycle {
    prevent_destroy = true
  }
}

# The pipeline role writes bronze, silver and gold. Its privileges are still granted by
# snowflake/01_setup.sql; Terraform owns the role and its place under SYSADMIN.
resource "snowflake_account_role" "pipeline" {
  provider = snowflake.security
  name     = "MEDIRELAIS_PIPELINE"
}

resource "snowflake_grant_account_role" "pipeline_to_sysadmin" {
  provider         = snowflake.security
  role_name        = snowflake_account_role.pipeline.name
  parent_role_name = "SYSADMIN"
}
