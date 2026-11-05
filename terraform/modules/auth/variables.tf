variable "name_prefix" {
  type = string
}

variable "region" {
  type = string
}

variable "lambda_role_arn" {
  type = string
}

variable "api_package_zip" {
  type = string
}

variable "api_package_hash" {
  type = string
}

variable "table_name" {
  type = string
}

variable "access_token_minutes" {
  type = number
}

variable "log_retention_days" {
  type = number
}
