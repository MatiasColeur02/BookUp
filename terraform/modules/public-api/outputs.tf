output "invoke_url" {
  description = "URL base del catálogo público (stage). Los endpoints cuelgan de acá: /books, /books/search, etc."
  value       = aws_api_gateway_stage.public.invoke_url
}

output "rest_api_id" {
  description = "Id del REST API (para métricas en CloudWatch, namespace ApiGateway)."
  value       = aws_api_gateway_rest_api.public.id
}

output "usage_plan_id" {
  description = "Id del usage plan que impone el throttling y la quota por cliente."
  value       = aws_api_gateway_usage_plan.public.id
}

output "api_key_ids" {
  description = "Id de la API key de cada consumidor (para `aws apigateway get-api-key --include-value`)."
  value       = { for name, key in aws_api_gateway_api_key.consumer : name => key.id }
}

# El valor en claro de cada API key. Sensible: va al state (ya privado) y se lee con
# `terraform output -raw` o `terraform output -json api_key_values`.
output "api_key_values" {
  description = "Valor en claro de la API key de cada consumidor (header x-api-key)."
  value       = { for name, key in aws_api_gateway_api_key.consumer : name => key.value }
  sensitive   = true
}

# Ejemplo listo para pegar en la demo (hay que reemplazar <API_KEY> por el valor real).
output "example_curl" {
  description = "Comando de ejemplo para consumir el catálogo con una API key."
  value       = "curl -s -H 'x-api-key: <API_KEY>' '${aws_api_gateway_stage.public.invoke_url}/books?limit=5'"
}
