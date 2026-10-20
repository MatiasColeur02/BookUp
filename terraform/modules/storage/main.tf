# Dos buckets públicos de solo lectura:
#   frontend → website hosting de la SPA (HTTP)
#   covers   → portadas; el browser las lee con <img> y las sube con un PUT firmado por la API
locals {
  buckets = {
    frontend = "${var.name_prefix}-frontend-${var.suffix}"
    covers   = "${var.name_prefix}-covers-${var.suffix}"
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this

  bucket                  = each.value.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "public_read" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadGetObject"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${each.value.arn}/*"
    }]
  })

  # Con el bloqueo de acceso público todavía activo, S3 rechaza una política pública.
  depends_on = [aws_s3_bucket_public_access_block.this]
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.this["frontend"].id

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
  bucket = aws_s3_bucket.this["covers"].id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = [local.frontend_url]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

locals {
  frontend_url = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}
