variable "name_prefix" {
  type = string
}

variable "region" {
  type = string
}

variable "account_id" {
  type = string
}

variable "subnet_ids" {
  description = "Subnets de datos (sin salida a Internet)."
  type        = list(string)
}

variable "redis_security_group_id" {
  type = string
}

variable "opensearch_security_group_id" {
  type = string
}

variable "dynamodb_pitr" {
  type = bool
}

variable "redis_node_type" {
  type = string
}

variable "redis_replicas" {
  type = number

  validation {
    condition     = var.redis_replicas >= 0 && var.redis_replicas <= 5
    error_message = "redis_replicas: entre 0 y 5."
  }
}

variable "opensearch_instance_type" {
  type = string
}

variable "opensearch_volume_size" {
  type = number
}

variable "create_opensearch_service_linked_role" {
  type = bool
}
