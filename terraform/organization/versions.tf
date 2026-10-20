terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State remoto en S3: el pipeline lo comparte entre corridas y el state nunca
  # vive en el runner. Configuración PARCIAL a propósito: `bucket` se pasa con
  # `-backend-config` desde el workflow de deploy, porque su nombre se deriva del
  # account id del lab (globalmente único) y no puede fijarse en el código.
  #
  # El state contiene el client secret de Cognito, por eso va a un bucket privado.
  #
  # Para validar/planear en local sin tocar el backend:
  #   terraform init -backend=false      # solo fmt/validate
  # o apuntando a tu propio bucket:
  #   terraform init -backend-config="bucket=mi-bucket-tfstate"
  backend "s3" {
    key          = "bookup/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true # bloqueo nativo de S3: evita que dos corridas pisen el state (sin DynamoDB)
  }
}
