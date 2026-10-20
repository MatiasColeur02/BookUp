variable "name_prefix" {
  type = string
}

variable "region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  description = "Subnets privadas (con NAT: la tarea baja la imagen de ECR Public)."
  type        = list(string)
}

variable "nlb_security_group_id" {
  type = string
}

variable "task_security_group_id" {
  type = string
}

variable "cluster_id" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "image" {
  type    = string
  default = "public.ecr.aws/opensearchproject/opensearch:2.17.1"
}

variable "port" {
  type = number
}

variable "cpu" {
  type = number
}

variable "memory" {
  description = "MiB. La mitad va al heap de la JVM."
  type        = number
}

variable "cpu_architecture" {
  type = string
}

variable "log_retention_days" {
  type = number
}
