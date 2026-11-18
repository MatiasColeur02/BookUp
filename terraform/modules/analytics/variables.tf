variable "name_prefix" {
  type = string
}

variable "suffix" {
  description = "Sufijo que hace único el nombre del bucket."
  type        = string
}

variable "region" {
  type = string
}

variable "force_destroy" {
  description = "Permite que terraform destroy borre el bucket aunque tenga objetos."
  type        = bool
  default     = true
}

variable "lambda_role_arn" {
  description = "Rol de la Lambda exportadora (LabRole: el Learner Lab no deja crear roles)."
  type        = string
}

variable "package_zip" {
  description = "Zip de api/ (el mismo que usan el indexador y las notificaciones)."
  type        = string
}

variable "package_hash" {
  type = string
}

variable "table_name" {
  description = "Tabla de DynamoDB de la que se exporta."
  type        = string
}

variable "export_minutes" {
  description = "Cada cuántos minutos se reescribe la foto de los datos en S3."
  type        = number
  default     = 60

  validation {
    condition     = var.export_minutes >= 1 && floor(var.export_minutes) == var.export_minutes
    error_message = "export_minutes: un entero ≥ 1."
  }
}

variable "athena_bytes_scanned_cutoff" {
  description = "Tope de bytes que puede escanear una query del workgroup (corta las que se pasan; mínimo de Athena: 10 MB)."
  type        = number
  default     = 1073741824

  validation {
    condition     = var.athena_bytes_scanned_cutoff >= 10485760
    error_message = "athena_bytes_scanned_cutoff: Athena exige al menos 10485760 (10 MB)."
  }
}

variable "log_retention_days" {
  type = number
}
