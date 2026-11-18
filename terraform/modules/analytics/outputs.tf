output "bucket" {
  description = "Bucket (privado) con la foto de los datos y los resultados de Athena."
  value       = terraform_data.bucket.output.name
}

output "exporter_function_name" {
  description = "Lambda que exporta DynamoDB a S3."
  value       = aws_lambda_function.exporter.function_name
}

output "database" {
  description = "Base del Glue Catalog con las tablas reservations, libraries y books."
  value       = aws_glue_catalog_database.analytics.name
}

output "workgroup" {
  description = "Workgroup de Athena (elegirlo en la consola antes de correr una query)."
  value       = aws_athena_workgroup.this.name
}

output "export_command" {
  description = "Exporta ya, sin esperar a la rule de EventBridge (útil justo después del deploy o del seed)."
  value       = "aws lambda invoke --region ${var.region} --function-name ${aws_lambda_function.exporter.function_name} --cli-binary-format raw-in-base64-out /dev/stdout"
}

output "example_query_command" {
  description = "Corre desde la CLI el reporte de reservas por sede y mes."
  value       = "aws athena start-query-execution --region ${var.region} --work-group ${aws_athena_workgroup.this.name} --query-execution-context Database=${aws_glue_catalog_database.analytics.name} --query-string 'SELECT library_name, reserved_month, count(*) AS reservas FROM reservations GROUP BY 1, 2 ORDER BY 2 DESC, 3 DESC'"
}
