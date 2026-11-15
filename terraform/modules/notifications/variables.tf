variable "name_prefix" {
  type = string
}

variable "lambda_role_arn" {
  description = "Rol de las tres Lambdas (LabRole: el Learner Lab no deja crear roles)."
  type        = string
}

variable "package_zip" {
  description = "Zip de api/ (el mismo que usan el indexador y el trigger de Cognito)."
  type        = string
}

variable "package_hash" {
  type = string
}

variable "table_name" {
  type = string
}

variable "table_stream_arn" {
  description = "Stream de la tabla (NEW_AND_OLD_IMAGES). El notificador es su segundo lector."
  type        = string
}

variable "deadline_scan_minutes" {
  description = "Cada cuántos minutos corre el job de vencimientos."
  type        = number
  default     = 15

  validation {
    condition     = var.deadline_scan_minutes >= 1 && floor(var.deadline_scan_minutes) == var.deadline_scan_minutes
    error_message = "deadline_scan_minutes: un entero ≥ 1."
  }
}

variable "retention_days" {
  description = "Días que vive una notificación en la bandeja (TTL de DynamoDB sobre ttl_epoch)."
  type        = number
  default     = 90

  validation {
    condition     = var.retention_days >= 1
    error_message = "retention_days: al menos 1 día."
  }
}

variable "timezone" {
  description = "Zona horaria de las fechas del texto de las notificaciones."
  type        = string
  default     = "America/Argentina/Buenos_Aires"
}

variable "log_retention_days" {
  type = number
}
