# These objects were created by hand (snowflake/01_setup.sql) before Terraform existed.
# Import blocks bring them under Terraform without recreating them: the first plan must
# show only "import", never "destroy" or "replace".

import {
  to = snowflake_warehouse.medirelais
  id = "\"MEDIRELAIS_WH\""
}

import {
  to = snowflake_database.medirelais
  id = "\"MEDIRELAIS\""
}

import {
  for_each = toset(["BRONZE", "SILVER", "GOLD"])
  to       = snowflake_schema.layer[each.key]
  id       = "\"MEDIRELAIS\".\"${each.key}\""
}

import {
  provider = snowflake.security
  to       = snowflake_account_role.pipeline
  id       = "\"MEDIRELAIS_PIPELINE\""
}

import {
  provider = snowflake.security
  to       = snowflake_grant_account_role.pipeline_to_sysadmin
  id       = "\"MEDIRELAIS_PIPELINE\"|ROLE|\"SYSADMIN\""
}
