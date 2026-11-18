# Reportes y analítica (TP1): un lugar aparte para sacar estadísticas sin cargar la app.
#
#   DynamoDB ──(Lambda exportadora, EventBridge)──▶ S3 (JSON Lines) ◀── Athena (Glue Catalog)
#
# DynamoDB no sabe agrupar ni sumar, y hacerlo desde la API competiría con las reservas. La
# Lambda deja una foto plana de los datos en S3 y Athena la consulta con SQL, pagando por lo que
# escanea y sin infraestructura prendida (Redshift es caro y está fuera del presupuesto del lab).
locals {
  bucket_name = "${var.name_prefix}-analytics-${var.suffix}"
}

# El bucket se crea con la CLI por la misma razón que los del módulo storage: aws_s3_bucket lee
# la configuración de Object Lock y el Learner Lab la deniega con una SCP.
resource "terraform_data" "bucket" {
  input = {
    name          = local.bucket_name
    arn           = "arn:aws:s3:::${local.bucket_name}"
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

# A diferencia de portadas y frontend, este bucket es privado: son datos de operación.
resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = terraform_data.bucket.output.name
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = terraform_data.bucket.output.name
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = terraform_data.bucket.output.name
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Los resultados de las queries son descartables: el historial vive en DynamoDB.
resource "aws_s3_bucket_lifecycle_configuration" "results" {
  bucket = terraform_data.bucket.output.name

  rule {
    id     = "expire-athena-results"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = 7
    }
  }
}

# --- Lambda exportadora ------------------------------------------------------
# Mismo zip que el indexador y las notificaciones, y fuera de la VPC: solo habla con DynamoDB y
# S3, que son endpoints públicos de AWS.
resource "aws_cloudwatch_log_group" "exporter" {
  name              = "/aws/lambda/${var.name_prefix}-analytics-exporter"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "exporter" {
  function_name    = "${var.name_prefix}-analytics-exporter"
  description      = "DynamoDB -> S3 (JSON Lines) para los reportes de Athena"
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = "app.analytics.exporter.handler"
  filename         = var.package_zip
  source_code_hash = var.package_hash
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      DYNAMO_TABLE     = var.table_name
      ANALYTICS_BUCKET = terraform_data.bucket.output.name
      S3_REGION        = var.region
    }
  }

  depends_on = [aws_cloudwatch_log_group.exporter]
}

# Una rule de EventBridge y no el Scheduler, por lo mismo que en notifications: la rule invoca
# la Lambda con un permiso basado en recursos y el Scheduler necesita un rol propio.
resource "aws_cloudwatch_event_rule" "export" {
  name                = "${var.name_prefix}-analytics-export"
  description         = "Refresca la foto de los datos que consulta Athena"
  schedule_expression = var.export_minutes == 1 ? "rate(1 minute)" : format("rate(%d minutes)", var.export_minutes)
}

resource "aws_cloudwatch_event_target" "export" {
  rule = aws_cloudwatch_event_rule.export.name
  arn  = aws_lambda_function.exporter.arn
}

resource "aws_lambda_permission" "events_exporter" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.exporter.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.export.arn
}
