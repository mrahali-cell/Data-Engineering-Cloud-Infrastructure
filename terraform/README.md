# Terraform: the MédiRelais platform as code

| File | What it declares |
| --- | --- |
| `versions.tf` | Pinned Terraform and provider versions; state in S3 (private, versioned, encrypted, locked while a run is in progress) |
| `providers.tf` | Snowflake as SYSADMIN for objects and SECURITYADMIN for roles and grants (never ACCOUNTADMIN); AWS in eu-north-1 |
| `platform.tf` | Warehouse `MEDIRELAIS_WH`, database `MEDIRELAIS`, schemas BRONZE/SILVER/GOLD (protected against deletion), the pipeline role |
| `roles.tf` | Who can read what: READER (the dashboard), FINANCE (with purchase prices), PHARMACIST_H01 and _H04 (their hospital only), all on GOLD only |
| `governance.tf` | The access rules on GOLD: pharmacists see their own hospital only (row access policies, driven by the `GOVERNANCE.HOSPITAL_ACCESS` mapping), purchase prices are hidden from everyone but FINANCE and the pipeline (masking policy). dbt re-attaches them after each rebuild (`medirelais_dbt/dbt_project.yml`); the dashboard is created by READER, so it shows every hospital and no prices |
| `archive.tf` | Where old raw data goes: S3 bucket, the access Snowflake uses to write to it, and the stage `MEDIRELAIS.BRONZE.ARCHIVE_STAGE` |
| `imports.tf` | Took over the objects first created by hand, without recreating them |

Not managed here, on purpose: tables (dbt owns silver and gold, the ingestion jobs own bronze), and the dbt project,
daily task and dashboard (deployed from Git by `snowflake/03_schedule.sql`).

## Change the platform

Bash:

```bash
cd terraform
export AWS_PROFILE=MediRelais
terraform plan
terraform apply
```

PowerShell:

```powershell
cd terraform
$env:AWS_PROFILE = "MediRelais"
terraform plan
terraform apply
```

Read the plan before typing `yes`. Never apply a plan that destroys or replaces the database or a schema:
that drops every table in it (the code refuses it, but do not remove that protection to get past it).
After a change, `terraform plan` must say "No changes"; anything else means someone changed Snowflake or AWS by hand.

## Manual steps (cannot be in Terraform)

- The Snowflake account and its first admin user.
- The AWS account and the state bucket `medirelais-tfstate-036158683687` (eu-north-1, versioning on, public access blocked).
  The AWS account only allows eu-north-1, so AWS resources are in Stockholm while Snowflake runs in Paris (AWS eu-west-3); both stay in the EU.
- The `TERRAFORM` service user, its key pair, and `GRANT CREATE INTEGRATION ON ACCOUNT TO ROLE SYSADMIN` (needs ACCOUNTADMIN): `bootstrap.sql`.
  The private key stays in `terraform/keys/`, ignored by git.
- The GitHub API integration (needs ACCOUNTADMIN): `snowflake/01_setup.sql`.

## Archive

Raw data that bronze no longer needs is copied every night to the bucket `medirelais-archive-036158683687`, one
folder per day, as Parquet. It stays readable for 90 days (replays, audits after an incident), then moves to Glacier,
then to Deep Archive after 1 year, where storage costs almost nothing. Reading a file back from Glacier needs a restore first.

How Snowflake writes to the bucket:

- **Today** (`archive_use_storage_integration = false`): the stage signs in as the IAM user
  `medirelais-snowflake-archive-writer`, allowed on this bucket only. Terraform creates its key and hands it to the stage;
  it is never typed and only lives in the encrypted state. Rotate it with
  `terraform apply -replace="aws_iam_access_key.snowflake_archive[0]"`.
- **Target**, already in the code: no key at all. Snowflake assumes an IAM role that trusts only our storage integration.
  The AWS account is on the Free plan, whose AWS-managed guardrails refuse that role to Snowflake's AWS account.
  After upgrading the plan, set the variable to `true` and apply: the user and its key are deleted and the stage uses the role.

The nightly archive task (last step of the Airflow DAG). The daily consumption files are append-only, so each run
copies the rows loaded that day; rerunning a day overwrites its folder. Parquet does not accept TIMESTAMP_LTZ, so
`_loaded_at` is written as UTC.

```sql
COPY INTO @MEDIRELAIS.BRONZE.ARCHIVE_STAGE/consumption_raw/dt={{ ds }}/
  FROM (SELECT * EXCLUDE (_loaded_at), CONVERT_TIMEZONE('UTC', _loaded_at)::TIMESTAMP_NTZ AS _loaded_at_utc
        FROM MEDIRELAIS.BRONZE.CONSUMPTION_RAW
        WHERE _loaded_at::DATE = '{{ ds }}'::DATE)
  FILE_FORMAT = (TYPE = PARQUET) HEADER = TRUE OVERWRITE = TRUE;
```
