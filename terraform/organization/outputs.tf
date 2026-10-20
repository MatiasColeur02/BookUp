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
