variable "aws_region" {
  description = "Región de AWS. El Learner Lab solo habilita us-east-1 y us-west-2."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Prefijo de todos los recursos."
  type        = string
  default     = "bookup"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.project))
    error_message = "project: minúsculas, números y guiones, de 2 a 16 caracteres."
  }
}

variable "environment" {
  description = "Nombre del entorno (va en los tags)."
  type        = string
  default     = "dev"
}

variable "name_suffix" {
  description = "Sufijo para los nombres globalmente únicos (buckets S3, dominio de Cognito). Vacío = uno aleatorio."
  type        = string
  default     = ""

  validation {
    condition     = var.name_suffix == "" || can(regex("^[a-z0-9-]{3,20}$", var.name_suffix))
    error_message = "name_suffix: minúsculas, números y guiones, de 3 a 20 caracteres."
  }
}

# --- Red ---------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR de la VPC. Las subredes salen de acá con cidrsubnet (/24)."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Cantidad de zonas de disponibilidad."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count: entre 2 y 3 (el ALB y ElastiCache Multi-AZ piden al menos 2)."
  }
}

variable "single_nat_gateway" {
  description = "true = un NAT compartido (más barato). false = un NAT por zona (alta disponibilidad)."
  type        = bool
  default     = true
}

# --- Datos -------------------------------------------------------------------

variable "dynamodb_pitr" {
  description = "Point-in-Time Recovery de la tabla."
  type        = bool
  default     = true
}

variable "redis_node_type" {
  description = "Tipo de nodo de ElastiCache."
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_replicas" {
  description = "Réplicas de Redis además del primario. Con 0 se apaga el Multi-AZ."
  type        = number
  default     = 1
}

variable "search_cpu" {
  description = "CPU de la tarea de OpenSearch (el Learner Lab no permite dominios gestionados)."
  type        = number
  default     = 1024
}

variable "search_memory" {
  description = "Memoria de la tarea de OpenSearch, en MiB. La mitad es heap de la JVM."
  type        = number
  default     = 2048
}

# --- Cómputo -----------------------------------------------------------------

variable "api_cpu" {
  description = "CPU de la tarea de Fargate (unidades: 1024 = 1 vCPU)."
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Memoria de la tarea de Fargate, en MiB."
  type        = number
  default     = 1024
}

variable "api_cpu_architecture" {
  description = "Arquitectura de la tarea: X86_64 o ARM64 (ARM64 evita la emulación al buildear en una Mac con Apple Silicon)."
  type        = string
  default     = "X86_64"
}

variable "api_desired_count" {
  description = "Tareas de la API corriendo."
  type        = number
  default     = 2
}

variable "run_seed" {
  description = "Correr app.seed + app.seed_cognito como tarea de ECS al terminar el apply."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Retención de los logs en CloudWatch."
  type        = number
  default     = 7
}

# --- Identidad ---------------------------------------------------------------

variable "access_token_minutes" {
  description = "Duración del access token de Cognito (igual a JWT_EXPIRE_MINUTES del modo local)."
  type        = number
  default     = 60
}

variable "force_destroy_buckets" {
  description = "Permite que terraform destroy borre los buckets aunque tengan objetos."
  type        = bool
  default     = true
}

variable "covers_noncurrent_days" {
  description = "Días que se conservan las versiones anteriores de las portadas (bucket versionado)."
  type        = number
  default     = 30

  validation {
    condition     = var.covers_noncurrent_days >= 1
    error_message = "covers_noncurrent_days: al menos 1 día."
  }
}
