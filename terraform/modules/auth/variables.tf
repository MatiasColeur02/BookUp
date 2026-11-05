variable "name_prefix" {
  type = string
}

variable "suffix" {
  description = "Hace único el prefijo del dominio de la Hosted UI."
  type        = string
}

variable "region" {
  type = string
}

variable "lambda_role_arn" {
  type = string
}

variable "frontend_url" {
  description = "Único destino de los redirects del puente."
  type        = string
}

variable "bridge_source_dir" {
  description = "Directorio auth-bridge/ del repo."
  type        = string
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
