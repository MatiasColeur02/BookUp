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

  # State local: contiene el client secret de Cognito y nunca va al repo (.gitignore).
  # Para compartirlo entre el grupo, un backend S3 en la cuenta del lab:
  #
  # backend "s3" {
  #   bucket = "bookup-tfstate-<sufijo>"
  #   key    = "bookup/terraform.tfstate"
  #   region = "us-east-1"
  # }
}
