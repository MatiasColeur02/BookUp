variable "name_prefix" {
  type = string
}

variable "region" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "azs" {
  type = list(string)
}

variable "single_nat_gateway" {
  type = bool
}

variable "search_port" {
  description = "Puerto HTTP de OpenSearch."
  type        = number
}

variable "api_port" {
  description = "Puerto del contenedor de la API (lo abre el SG de las tareas desde el ALB)."
  type        = number
}
