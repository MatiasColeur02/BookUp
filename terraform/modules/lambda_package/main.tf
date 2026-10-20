# Empaqueta api/ (código + dependencias de requirements.txt para Linux x86_64) en un zip que
# comparten las dos Lambdas que reutilizan el código de la API: el indexador y el trigger
# Post Confirmation de Cognito.
locals {
  build_dir = "${path.root}/.build/${var.name}"
  zip_path  = "${path.root}/.build/${var.name}.zip"

  # Cambia cuando cambia el código o las dependencias: dispara el rebuild.
  source_hash = sha1(join("", concat(
    [filesha1("${var.source_dir}/requirements.txt")],
    [for f in sort(fileset("${var.source_dir}/app", "**/*.py")) : filesha1("${var.source_dir}/app/${f}")],
  )))
}

resource "terraform_data" "build" {
  # Si el directorio de build no existe (clon nuevo), se rearma aunque el código no cambie.
  triggers_replace = [
    local.source_hash,
    fileexists("${local.build_dir}/app/__init__.py") ? "present" : timestamp(),
  ]

  provisioner "local-exec" {
    command = "${path.module}/build.sh"
    environment = {
      SOURCE_DIR     = var.source_dir
      BUILD_DIR      = local.build_dir
      PYTHON_VERSION = var.python_version
    }
  }
}

data "archive_file" "this" {
  type        = "zip"
  source_dir  = local.build_dir
  output_path = local.zip_path

  # Se lee recién después del build, no en el plan.
  depends_on = [terraform_data.build]
}
