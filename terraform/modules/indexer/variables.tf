variable "name_prefix" {
  type = string
}

variable "lambda_role_arn" {
  type = string
}

variable "package_zip" {
  type = string
}

variable "package_hash" {
  type = string
}

variable "stream_arn" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "environment" {
  description = "Variables de entorno de la Lambda."
  type        = map(string)
}

variable "log_retention_days" {
  type = number
}
