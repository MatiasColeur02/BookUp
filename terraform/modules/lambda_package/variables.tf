variable "name" {
  description = "Nombre del paquete (directorio y zip en terraform/.build/)."
  type        = string
}

variable "source_dir" {
  description = "Directorio con app/ y requirements.txt."
  type        = string
}

variable "python_version" {
  description = "Versión de Python del runtime de Lambda, para elegir los wheels."
  type        = string
  default     = "3.12"
}
