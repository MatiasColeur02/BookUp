# Indexador: stream de DynamoDB → OpenSearch (api/app/indexer.py, handler). Corre en la VPC
# porque OpenSearch y Redis están en subnets de datos; llega a DynamoDB por el gateway endpoint.
resource "aws_cloudwatch_log_group" "indexer" {
  name              = "/aws/lambda/${var.name_prefix}-indexer"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "indexer" {
  function_name    = "${var.name_prefix}-indexer"
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = "app.indexer.handler"
  filename         = var.package_zip
  source_code_hash = var.package_hash
  timeout          = 60
  memory_size      = 512

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.security_group_id]
  }

  environment {
    variables = var.environment
  }

  depends_on = [aws_cloudwatch_log_group.indexer]
}

# Lote que falla después de los reintentos: su metadata va acá en vez de congelar el shard.
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-indexer-dlq"
  message_retention_seconds = 1209600 # 14 días
  sqs_managed_sse_enabled   = true
}

resource "aws_lambda_event_source_mapping" "stream" {
  event_source_arn  = var.stream_arn
  function_name     = aws_lambda_function.indexer.arn
  starting_position = "LATEST"

  batch_size                         = 100
  maximum_batching_window_in_seconds = 1
  # Un evento venenoso se aísla partiendo el lote en vez de bloquear todo el shard.
  bisect_batch_on_function_error = true
  maximum_retry_attempts         = 5

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.dlq.arn
    }
  }
}
