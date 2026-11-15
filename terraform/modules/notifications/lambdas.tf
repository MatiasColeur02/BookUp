# Las tres Lambdas de las notificaciones (notifications-roadmap.md §3). Mismo zip que el
# indexador, y **fuera de la VPC** (§3.5): solo hablan con DynamoDB y SNS, que son endpoints
# públicos de AWS; así no ocupan ENIs ni pasan por el NAT.
locals {
  functions = {
    # Stream → detecta la transición de la reserva → publica en SNS.
    notifier = {
      handler     = "app.notifications.notifier.handler"
      description = "Stream de DynamoDB -> eventos de reservas en SNS"
      timeout     = 60
    }
    # SNS → arma el texto y escribe las dos notificaciones (lector y sede).
    inbox-writer = {
      handler     = "app.notifications.inbox_writer.handler"
      description = "SNS -> bandejas del lector y de la sede"
      timeout     = 30
    }
    # EventBridge → marca los plazos vencidos (el aviso sale por el stream).
    deadline-scanner = {
      handler     = "app.notifications.deadline_scanner.handler"
      description = "Marca las reservas con el plazo vencido"
      timeout     = 120
    }
  }

  # Las tres leen la misma configuración (api/app/config.py). `NOTIFICATIONS_BUS = sns` exige
  # el ARN del topic: sin él `Settings` falla al importar en vez de perder eventos en silencio.
  environment = {
    DYNAMO_TABLE                 = var.table_name
    NOTIFICATIONS_BUS            = "sns"
    NOTIFICATIONS_TOPIC_ARN      = aws_sns_topic.reservation_events.arn
    NOTIFICATIONS_RETENTION_DAYS = tostring(var.retention_days)
    NOTIFICATIONS_TIMEZONE       = var.timezone
  }
}

resource "aws_cloudwatch_log_group" "this" {
  for_each = local.functions

  name              = "/aws/lambda/${var.name_prefix}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  for_each = local.functions

  function_name    = "${var.name_prefix}-${each.key}"
  description      = each.value.description
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = each.value.handler
  filename         = var.package_zip
  source_code_hash = var.package_hash
  timeout          = each.value.timeout
  memory_size      = 256

  environment {
    variables = local.environment
  }

  depends_on = [aws_cloudwatch_log_group.this]
}

# El notificador es el segundo lector del stream (el primero es el indexador; DynamoDB Streams
# admite dos sin throttling). Un consumidor nuevo se cuelga de SNS, no de acá.
resource "aws_lambda_event_source_mapping" "notifier" {
  event_source_arn  = var.table_stream_arn
  function_name     = aws_lambda_function.this["notifier"].arn
  starting_position = "LATEST"

  batch_size                         = 100
  maximum_batching_window_in_seconds = 1
  # El handler lanza ante un error (no devuelve batchItemFailures): partir el lote aísla el
  # registro venenoso, y con el tope de reintentos se saltea en vez de congelar el shard (y con
  # él las notificaciones de todas las reservas). Sin destino de fallos: se pierde el aviso,
  # nunca la reserva (§13).
  bisect_batch_on_function_error = true
  maximum_retry_attempts         = 5

  # Sin filtro, la Lambda se invocaría por cada escritura de la tabla. Los filtros se combinan
  # con OR; lo que no matchea se descarta antes de invocar.
  filter_criteria {
    # La reserva en sí (no los enlaces RES# bajo otras particiones).
    filter {
      pattern = jsonencode({
        dynamodb = {
          Keys = {
            PK = { S = [{ prefix = "RES#" }] }
            SK = { S = ["META"] }
          }
        }
      })
    }

    # El borrado por TTL de una notificación: si no estaba leída, descuenta del contador (§5.3).
    filter {
      pattern = jsonencode({
        eventName = ["REMOVE"]
        userIdentity = {
          type        = ["Service"]
          principalId = ["dynamodb.amazonaws.com"]
        }
        dynamodb = {
          Keys = {
            PK = { S = [{ prefix = "INBOX#" }] }
            SK = { S = [{ prefix = "NOTIF#" }] }
          }
        }
      })
    }
  }
}
