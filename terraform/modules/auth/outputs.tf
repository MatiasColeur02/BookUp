output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "client_id" {
  description = "App client público que usan el frontend y la API (valida el client_id del token)."
  value       = aws_cognito_user_pool_client.web.id
}
