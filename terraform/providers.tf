# Credenciales: las de "AWS Details" del Learner Lab (~/.aws/credentials o variables de
# entorno). Vencen con la sesión; si un apply se corta, volver a correrlo converge.
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}
