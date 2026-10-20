resource "aws_ecr_repository" "api" {
  name                 = "${var.name_prefix}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Conservar las ultimas 5 imagenes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

locals {
  # El tag de la imagen es el hash del código: un cambio en api/ es una imagen nueva y, por
  # lo tanto, una task definition nueva y un deploy.
  image_files = concat(
    ["Dockerfile", "requirements.txt", "requirements-dev.txt"],
    [for f in fileset(var.api_source_dir, "app/**/*.py") : f],
  )
  image_tag = substr(sha1(join("", [for f in sort(local.image_files) : filesha1("${var.api_source_dir}/${f}")])), 0, 12)
  image_uri = "${aws_ecr_repository.api.repository_url}:${local.image_tag}"
}

# docker build + push desde la máquina que corre Terraform (necesita Docker).
resource "terraform_data" "image" {
  triggers_replace = [local.image_uri]

  provisioner "local-exec" {
    command = "${path.module}/push_image.sh"
    environment = {
      REGION     = var.region
      REGISTRY   = split("/", aws_ecr_repository.api.repository_url)[0]
      IMAGE_URI  = local.image_uri
      SOURCE_DIR = var.api_source_dir
      PLATFORM   = var.cpu_architecture == "ARM64" ? "linux/arm64" : "linux/amd64"
    }
  }
}
