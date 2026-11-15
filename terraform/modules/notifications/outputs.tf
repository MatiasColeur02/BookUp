output "topic_arn" {
  description = "Topic SNS de los eventos de reservas (para suscribir canales nuevos)."
  value       = aws_sns_topic.reservation_events.arn
}

output "function_names" {
  description = "Nombre de cada Lambda, por rol (notifier, inbox-writer, deadline-scanner)."
  value       = { for key, fn in aws_lambda_function.this : key => fn.function_name }
}

output "schedule_rule" {
  description = "Rule de EventBridge que dispara el job de vencimientos."
  value       = aws_cloudwatch_event_rule.deadline_scan.name
}
