variable "name_prefix" {
  description = "Prefijo de todos los recursos."
  type        = string
}

variable "backend_base_url" {
  description = "URL base del backend al que se hace proxy, sin barra final (el ALB de la API, p. ej. http://bookup-alb-123.us-east-1.elb.amazonaws.com)."
  type        = string

  validation {
    condition     = can(regex("^https?://[^/]+$", var.backend_base_url))
    error_message = "backend_base_url: un origen http(s) sin path ni barra final (http://host o https://host)."
  }
}

variable "stage_name" {
  description = "Nombre del stage del API público (va en la URL de invocación)."
  type        = string
  default     = "v1"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]{1,64}$", var.stage_name))
    error_message = "stage_name: letras, números, guiones y guiones bajos."
  }
}

variable "external_consumers" {
  description = "Consumidores externos: por cada nombre se crea una API key ligada al usage plan. El nombre va en el nombre de la clave."
  type        = set(string)
  default     = ["demo-library"]

  validation {
    condition     = length(var.external_consumers) >= 1
    error_message = "external_consumers: al menos un consumidor (si no, nadie puede consumir el API)."
  }
}

# --- Límites por cliente (usage plan) ----------------------------------------
# Throttling y quota se cuentan por API key, así que son el límite de CADA cliente.

variable "consumer_rate_limit" {
  description = "Requests por segundo sostenidos por API key (throttling del usage plan)."
  type        = number
  default     = 20
}

variable "consumer_burst_limit" {
  description = "Ráfaga máxima de requests por API key (burst del usage plan)."
  type        = number
  default     = 40
}

variable "consumer_quota_limit" {
  description = "Cuota de requests por API key en el período (quota del usage plan)."
  type        = number
  default     = 10000
}

variable "consumer_quota_period" {
  description = "Período de la cuota: DAY, WEEK o MONTH."
  type        = string
  default     = "MONTH"

  validation {
    condition     = contains(["DAY", "WEEK", "MONTH"], var.consumer_quota_period)
    error_message = "consumer_quota_period: DAY, WEEK o MONTH."
  }
}

# --- Techo del stage ---------------------------------------------------------
# Límite agregado del stage (todas las claves juntas), como red de seguridad del backend.

variable "stage_throttle_rate_limit" {
  description = "Requests por segundo sostenidos del stage completo (todas las claves)."
  type        = number
  default     = 100
}

variable "stage_throttle_burst_limit" {
  description = "Ráfaga máxima del stage completo (todas las claves)."
  type        = number
  default     = 200
}
