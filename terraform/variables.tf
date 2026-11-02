variable "snowflake_organization" {
  description = "Snowflake organization name (first part of the account URL)"
  type        = string
  default     = "EUNCQZI"
}

variable "snowflake_account" {
  description = "Snowflake account name (second part of the account URL)"
  type        = string
  default     = "UO99407"
}

variable "snowflake_user" {
  description = "Service user Terraform logs in with (created by bootstrap.sql)"
  type        = string
  default     = "TERRAFORM"
}

variable "archive_use_storage_integration" {
  description = "true = Snowflake reaches the archive bucket through the IAM role (keyless). false = through a bucket-only IAM user, while the AWS Free plan blocks the role (see archive.tf)"
  type        = bool
  default     = false
}

variable "snowflake_private_key_path" {
  description = "Path to the user's private key; the file stays out of git (terraform/keys/)"
  type        = string
  default     = "keys/terraform_rsa_key.p8"
}
