variable "name_prefix" {
  type = string
}

variable "suffix" {
  description = "Sufijo que hace únicos los nombres de bucket."
  type        = string
}

variable "force_destroy" {
  type = bool
}

variable "region" {
  type = string
}

variable "covers_noncurrent_days" {
  description = "Días que se conserva una versión anterior de una portada antes de borrarse."
  type        = number
}
