output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "cognito_domain" {
  description = "Host de la Hosted UI (sin esquema)."
  value       = local.cognito_domain
}

output "callback_url" {
  value = local.callback_url
}

output "signed_out_url" {
  value = local.signed_out_url
}
