output "frontend_bucket" {
  value = aws_s3_bucket.this["frontend"].id
}

output "covers_bucket" {
  value = aws_s3_bucket.this["covers"].id
}

output "frontend_url" {
  description = "Website endpoint del frontend (HTTP, sin barra final)."
  value       = local.frontend_url
}
