# El bus de eventos de reservas (notifications-roadmap.md §3.2). Estándar, no FIFO: el orden
# no importa y la idempotencia está en la bandeja (el id de cada notificación sale del evento).
resource "aws_sns_topic" "reservation_events" {
  name = "${var.name_prefix}-reservation-events"
  # Clave gestionada por AWS: su key policy ya habilita a SNS y a los principales de la cuenta,
  # así que no hace falta una clave propia (que pediría una policy que el lab no deja editar).
  kms_master_key_id = "alias/aws/sns"
}

# El inbox-writer, suscripto directo (sin SQS, §3.3): SNS lo invoca de forma asíncrona y Lambda
# reintenta 2 veces lo que falle dentro de la función.
resource "aws_sns_topic_subscription" "inbox_writer" {
  topic_arn = aws_sns_topic.reservation_events.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.this["inbox-writer"].arn
}

# Sin este permiso SNS no puede invocar la Lambda y la suscripción falla en silencio.
resource "aws_lambda_permission" "sns_inbox_writer" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this["inbox-writer"].function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.reservation_events.arn
}
