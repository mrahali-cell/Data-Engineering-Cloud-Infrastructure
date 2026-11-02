# Terraform: the Snowflake platform as code

| File | What it declares |
| --- | --- |
| `versions.tf` | Pinned Terraform and provider versions; remote state in S3 (private, versioned, encrypted, locked) |
| `providers.tf` | Two Snowflake connections: SYSADMIN for objects, SECURITYADMIN for roles and grants (no ACCOUNTADMIN) |
| `imports.tf` | Brings the objects created by hand (warehouse, database, 3 schemas, pipeline role) under Terraform without recreating them |
| `platform.tf` | Warehouse `MEDIRELAIS_WH`, database `MEDIRELAIS`, schemas BRONZE/SILVER/GOLD (with `prevent_destroy`), the pipeline role |
| `roles.tf` | Governance roles READER, FINANCE, PHARMACIST_H01, PHARMACIST_H04 and their read access to GOLD |

What Terraform does **not** manage, on purpose: tables (dbt owns silver and gold, the ingestion SQL owns bronze),
and the dbt project, daily task and dashboard (deployed from Git by `snowflake/03_schedule.sql`).

## Run it

```bash
cd terraform
export AWS_PROFILE=MediRelais   # credentials for the state bucket (aws login)
terraform init                  # downloads the provider, connects to the S3 backend
terraform plan                  # shows what would change; changes nothing
terraform apply                 # only after reading the plan: never apply a "destroy" or "replace" on the database
terraform plan                  # "No changes" = Snowflake matches the code (no drift)
```
