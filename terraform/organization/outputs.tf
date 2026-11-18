output "frontend_url" {
  description = "La plataforma (website endpoint de S3, HTTP)."
  value       = module.storage.frontend_url
}

output "frontend_bucket" {
  description = "Bucket donde se sube el build del frontend."
  value       = module.storage.frontend_bucket
}

output "api_url" {
  description = "La API (DNS del ALB, HTTP). Health check en /health."
  value       = module.compute.api_url
}

output "auth_bridge_url" {
  description = "API Gateway del puente HTTPS de Cognito."
  value       = trimsuffix(module.auth.callback_url, "/callback")
}

output "cognito_user_pool_id" {
  value = module.auth.user_pool_id
}

output "cognito_client_id" {
  value = module.auth.client_id
}

output "cognito_domain" {
  value = module.auth.cognito_domain
}

output "ecr_image" {
  value = module.compute.image_uri
}

output "reindex_command" {
  description = "Reconstruye el índice de OpenSearch (necesario si la tarea de búsqueda se reemplazó)."
  value       = module.compute.reindex_command
}

output "indexer_dlq_url" {
  value = module.indexer.dlq_url
}

output "notifications_topic_arn" {
  description = "Topic SNS de los eventos de reservas."
  value       = module.notifications.topic_arn
}

output "notifications_functions" {
  description = "Lambdas de las notificaciones (para `aws logs tail /aws/lambda/<nombre>`)."
  value       = module.notifications.function_names
}

output "public_api_url" {
  description = "Catálogo público para bibliotecas externas (API Gateway, solo lectura, pide x-api-key)."
  value       = module.public_api.invoke_url
}

# Valores en claro de las API keys de los consumidores externos. Sensible.
#   terraform output -json public_api_keys
output "public_api_keys" {
  description = "Valor de la API key de cada consumidor externo del catálogo (header x-api-key)."
  value       = module.public_api.api_key_values
  sensitive   = true
}

output "public_api_example" {
  description = "Ejemplo de consumo del catálogo público (reemplazar <API_KEY> por el valor real)."
  value       = module.public_api.example_curl
}

output "analytics_database" {
  description = "Base de Athena (Glue Catalog) con las tablas reservations, libraries y books."
  value       = module.analytics.database
}

output "analytics_workgroup" {
  description = "Workgroup de Athena de los reportes."
  value       = module.analytics.workgroup
}

output "analytics_export_command" {
  description = "Refresca ya la foto de los datos (si no, la rule de EventBridge lo hace cada hora)."
  value       = module.analytics.export_command
}

output "analytics_example_query_command" {
  description = "Corre desde la CLI el reporte de reservas por sede y mes."
  value       = module.analytics.example_query_command
}

# Listo para `terraform output -raw frontend_env > ../frontend/.env.production`.
output "frontend_env" {
  description = "Variables VITE_* del build del frontend."
  value = join("\n", [for name, value in {
    VITE_API_URL             = module.compute.api_url
    VITE_AUTH_MODE           = "cognito"
    VITE_COGNITO_DOMAIN      = module.auth.cognito_domain
    VITE_COGNITO_CLIENT_ID   = module.auth.client_id
    VITE_AUTH_CALLBACK_URL   = module.auth.callback_url
    VITE_AUTH_SIGNED_OUT_URL = module.auth.signed_out_url
  } : "${name}=${value}"])
}
