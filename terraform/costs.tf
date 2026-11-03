# Cost visibility: every Snowflake object that bills carries the project's cost center, so the
# bill can be split by project (snowflake/05_costs.sql). Queries carry a query tag on top
# (dbt: medirelais_dbt/dbt_project.yml), which splits the warehouse bill by job.
# AWS resources are tagged by the provider's default_tags (providers.tf).
resource "snowflake_tag" "cost_center" {
  database               = snowflake_database.medirelais.name
  schema                 = snowflake_schema.governance.name
  name                   = "COST_CENTER"
  ordered_allowed_values = ["medirelais"]
  comment                = "Who pays for this object"
}

resource "snowflake_tag_association" "cost_center" {
  for_each = {
    WAREHOUSE = snowflake_warehouse.medirelais.fully_qualified_name
    DATABASE  = snowflake_database.medirelais.fully_qualified_name
  }
  object_type        = each.key
  object_identifiers = [each.value]
  tag_id             = snowflake_tag.cost_center.fully_qualified_name
  tag_value          = "medirelais"
}
