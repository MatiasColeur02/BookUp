# El job de vencimientos (notifications-roadmap.md §3.4). Una **rule** de EventBridge y no
# EventBridge Scheduler: la rule invoca la Lambda con un permiso basado en recursos, y el
# Scheduler necesita un rol propio que asumir (el Learner Lab no deja crear roles).
resource "aws_cloudwatch_event_rule" "deadline_scan" {
  name        = "${var.name_prefix}-deadline-scan"
  description = "Dispara el deadline-scanner de las notificaciones de reservas"
  # EventBridge exige el singular para 1 («rate(1 minute)»).
  schedule_expression = var.deadline_scan_minutes == 1 ? "rate(1 minute)" : format("rate(%d minutes)", var.deadline_scan_minutes)
}

resource "aws_cloudwatch_event_target" "deadline_scan" {
  rule = aws_cloudwatch_event_rule.deadline_scan.name
  arn  = aws_lambda_function.this["deadline-scanner"].arn

  # El job escribe una marca y el aviso sale por el stream: si corriera antes de que el
  # notificador esté enganchado (arranca en LATEST), esa marca no notificaría nunca.
  depends_on = [aws_lambda_event_source_mapping.notifier]
}

resource "aws_lambda_permission" "events_deadline_scanner" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this["deadline-scanner"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.deadline_scan.arn
}
