# Classification: every table says who owns it, how sensitive it is, whether it holds personal
# data, and how long it is kept. Snowsight shows the result under Governance & Security.
#
#   Layer    Who sets the tags                   Why
#   BRONZE   Terraform (below)                   tables are created once and never rebuilt
#   SILVER   dbt, after each build               dbt recreates these tables every night,
#   GOLD     (macros/governance_tags.sql)        which drops any tag set on them
#
# Schemas carry the same tags, so a new table is classified by inheritance until it gets its own.

locals {
  tag_values = {
    DATA_OWNER  = ["manel.rahali", "hadiqa.javaid", "soumaya.atoui"]
    SENSITIVITY = ["public", "internal", "confidential"]
    PII         = ["none", "indirect", "direct"]
    RETENTION   = ["kept_as_received", "rebuilt_daily"]
  }

  tag_comments = {
    DATA_OWNER  = "Steward accountable for the definitions and the quality of the data"
    SENSITIVITY = "public: open government data; internal: team only; confidential: negotiated prices"
    PII         = "Personal data: none on this platform (no patients, no staff)"
    RETENTION   = "kept_as_received: append-only raw data; rebuilt_daily: recreated by dbt each night"
  }

  # Schema -> tag values (inherited by every table in the schema)
  schema_tags = {
    BRONZE     = { DATA_OWNER = "manel.rahali", SENSITIVITY = "confidential", PII = "none", RETENTION = "kept_as_received" }
    SILVER     = { DATA_OWNER = "hadiqa.javaid", SENSITIVITY = "confidential", PII = "none", RETENTION = "rebuilt_daily" }
    GOLD       = { DATA_OWNER = "hadiqa.javaid", SENSITIVITY = "internal", PII = "none", RETENTION = "rebuilt_daily" }
    GOVERNANCE = { DATA_OWNER = "soumaya.atoui", SENSITIVITY = "internal", PII = "none", RETENTION = "kept_as_received" }
  }

  # Bronze tables (created by ingestion/sql/bronze_sources.sql) -> sensitivity
  bronze_sensitivity = {
    HOSPITALS_RAW          = "internal"
    PRODUCTS_RAW           = "confidential" # negotiated purchase prices
    STOCK_RAW              = "internal"
    CONSUMPTION_RAW        = "internal"
    BDPM_SPECIALITES_RAW   = "public" # open drug database (ANSM)
    BDPM_PRESENTATIONS_RAW = "public"
    BDPM_COMPOSITION_RAW   = "public"
    SHORTAGES_RAW          = "public" # open shortage list (ANSM)
    LOAD_RUNS              = "internal"
  }

  schema_fqn = merge(
    { for s, r in snowflake_schema.layer : s => r.fully_qualified_name },
    { GOVERNANCE = snowflake_schema.governance.fully_qualified_name }
  )

  # One association per (tag, value): Snowflake groups objects that share a value
  schema_assoc = merge([
    for tag in keys(local.tag_values) : {
      for value in distinct([for s, t in local.schema_tags : t[tag]]) :
      "${tag}=${value}" => {
        tag     = tag
        value   = value
        objects = [for s, t in local.schema_tags : local.schema_fqn[s] if t[tag] == value]
      }
    }
  ]...)

  bronze_table_fqn = { for t in keys(local.bronze_sensitivity) : t => "\"${snowflake_database.medirelais.name}\".\"BRONZE\".\"${t}\"" }

  bronze_assoc = merge(
    {
      "DATA_OWNER=manel.rahali"    = { tag = "DATA_OWNER", value = "manel.rahali", objects = values(local.bronze_table_fqn) }
      "PII=none"                   = { tag = "PII", value = "none", objects = values(local.bronze_table_fqn) }
      "RETENTION=kept_as_received" = { tag = "RETENTION", value = "kept_as_received", objects = values(local.bronze_table_fqn) }
    },
    {
      for value in distinct(values(local.bronze_sensitivity)) :
      "SENSITIVITY=${value}" => {
        tag     = "SENSITIVITY"
        value   = value
        objects = [for t, s in local.bronze_sensitivity : local.bronze_table_fqn[t] if s == value]
      }
    }
  )
}

resource "snowflake_tag" "classification" {
  for_each               = local.tag_values
  database               = snowflake_database.medirelais.name
  schema                 = snowflake_schema.governance.name
  name                   = each.key
  ordered_allowed_values = each.value
  comment                = local.tag_comments[each.key]
}

resource "snowflake_tag_association" "schemas" {
  for_each           = local.schema_assoc
  object_type        = "SCHEMA"
  object_identifiers = each.value.objects
  tag_id             = snowflake_tag.classification[each.value.tag].fully_qualified_name
  tag_value          = each.value.value
}

resource "snowflake_tag_association" "bronze_tables" {
  for_each           = local.bronze_assoc
  object_type        = "TABLE"
  object_identifiers = each.value.objects
  tag_id             = snowflake_tag.classification[each.value.tag].fully_qualified_name
  tag_value          = each.value.value
}

# The column that holds negotiated prices, at the source
resource "snowflake_tag_association" "bronze_price_column" {
  object_type        = "COLUMN"
  object_identifiers = ["${local.bronze_table_fqn["PRODUCTS_RAW"]}.\"UNIT_COST_EUR\""]
  tag_id             = snowflake_tag.classification["SENSITIVITY"].fully_qualified_name
  tag_value          = "confidential"
}

# dbt tags the silver and gold tables it rebuilds: it may apply these tags, nothing more
resource "snowflake_grant_privileges_to_account_role" "pipeline_apply_tags" {
  provider          = snowflake.security
  for_each          = snowflake_tag.classification
  account_role_name = snowflake_account_role.pipeline.name
  privileges        = ["APPLY"]
  on_schema_object {
    object_type = "TAG"
    object_name = each.value.fully_qualified_name
  }
}
