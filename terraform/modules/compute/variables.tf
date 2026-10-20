variable "name_prefix" {
  type = string
}

variable "region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "alb_security_group_id" {
  type = string
}

variable "app_security_group_id" {
  type = string
}

variable "cluster_id" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "task_role_arn" {
  description = "Rol de ejecución y de tarea (LabRole)."
  type        = string
}

variable "api_source_dir" {
  description = "Directorio api/ del repo (contexto del docker build)."
  type        = string
}

variable "api_port" {
  type = number
}

variable "cpu" {
  type = number
}

variable "memory" {
  type = number
}

variable "cpu_architecture" {
  description = "X86_64 o ARM64. Define también la plataforma del docker build."
  type        = string
  default     = "X86_64"

  validation {
    condition     = contains(["X86_64", "ARM64"], var.cpu_architecture)
    error_message = "cpu_architecture: X86_64 o ARM64."
  }
}

variable "desired_count" {
  type = number
}

variable "environment" {
  description = "Variables de entorno del contenedor."
  type        = map(string)
}

variable "log_retention_days" {
  type = number
}

variable "run_seed" {
  type = bool
}

variable "seed_trigger" {
  description = "Valor que, al cambiar, vuelve a correr el seed (p. ej. el ARN de la tabla)."
  type        = string
}
