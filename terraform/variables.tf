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

variable "snowflake_private_key_path" {
  description = "Path to the user's private key; the file stays out of git (terraform/keys/)"
  type        = string
  default     = "keys/terraform_rsa_key.p8"
}
