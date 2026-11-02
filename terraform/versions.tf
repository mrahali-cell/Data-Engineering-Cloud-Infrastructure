# Terraform and provider versions are pinned (same reflex as Docker images).
# State lives in S3, never in git: private, versioned, encrypted, locked during each run.
# The state bucket itself is a manual step (it must exist before Terraform can use it).
terraform {
  required_version = ">= 1.10"

  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.22"
    }
  }

  backend "s3" {
    bucket       = "medirelais-tfstate-036158683687"
    key          = "snowflake/terraform.tfstate"
    region       = "eu-north-1" # the account's guardrail policy only allows this region
    encrypt      = true
    use_lockfile = true # S3-native lock: two people cannot apply at the same time
  }
}
