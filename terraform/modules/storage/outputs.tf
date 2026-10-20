output "frontend_bucket" {
  value = terraform_data.bucket["frontend"].output.name
}

output "covers_bucket" {
  value = terraform_data.bucket["covers"].output.name
}

output "frontend_url" {
  description = "Website endpoint del frontend (HTTP, sin barra final)."
  value       = local.frontend_url
}
