# Dos buckets públicos de solo lectura:
#   frontend → website hosting de la SPA (HTTP)
#   covers   → portadas; el browser las lee con <img> y las sube con un PUT firmado por la API
locals {
  buckets = {
    frontend = "${var.name_prefix}-frontend-${var.suffix}"
    covers   = "${var.name_prefix}-covers-${var.suffix}"
  }
}

# El bucket se crea con la CLI y no con aws_s3_bucket: ese recurso lee la configuración de
# Object Lock en cada refresh, y el Learner Lab la deniega con una SCP
# (s3:GetBucketObjectLockConfiguration). El resto de la configuración sí son recursos nativos.
resource "terraform_data" "bucket" {
  for_each = local.buckets

  input = {
    name          = each.value
    arn           = "arn:aws:s3:::${each.value}"
    region        = var.region
    force_destroy = var.force_destroy
  }

  provisioner "local-exec" {
    command = "${path.module}/bucket.sh create"
    environment = {
      BUCKET = self.input.name
      REGION = self.input.region
    }
  }

  provisioner "local-exec" {
    when    = destroy
    command = "${path.module}/bucket.sh delete"
    environment = {
      BUCKET        = self.input.name
      REGION        = self.input.region
      FORCE_DESTROY = tostring(self.input.force_destroy)
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = terraform_data.bucket

  bucket = each.value.output.name
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = terraform_data.bucket

  bucket = each.value.output.name
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = terraform_data.bucket

  bucket                  = each.value.output.name
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "public_read" {
  for_each = terraform_data.bucket

  bucket = each.value.output.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadGetObject"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${each.value.output.arn}/*"
    }]
  })

  # Con el bloqueo de acceso público todavía activo, S3 rechaza una política pública.
  depends_on = [aws_s3_bucket_public_access_block.this]
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = terraform_data.bucket["frontend"].output.name

  index_document {
    suffix = "index.html"
  }

  # SPA con React Router: una ruta interna recargada vuelve al index.
  error_document {
    key = "index.html"
  }
}

# El PUT de la portada va directo del browser al bucket: sin CORS el browser lo bloquea.
resource "aws_s3_bucket_cors_configuration" "covers" {
  bucket = terraform_data.bucket["covers"].output.name

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = [local.frontend_url]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Versionado de las portadas: reemplazar o borrar una portada no pierde la imagen anterior.
# La API borra el objeto viejo al reemplazar; con versionado eso deja un delete marker y la
# versión previa queda como no-actual hasta que la expira la regla de lifecycle de abajo.
resource "aws_s3_bucket_versioning" "covers" {
  bucket = terraform_data.bucket["covers"].output.name

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "covers" {
  bucket = terraform_data.bucket["covers"].output.name

  rule {
    id     = "expire-noncurrent-covers"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.covers_noncurrent_days
    }

    # Delete markers que ya no tapan ninguna versión.
    expiration {
      expired_object_delete_marker = true
    }

    # Un PUT firmado que el browser cortó a mitad no queda ocupando espacio.
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  # Las reglas de lifecycle se evalúan sobre un bucket ya versionado.
  depends_on = [aws_s3_bucket_versioning.covers]
}

locals {
  frontend_url = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}
