output "table_name" {
  value = aws_dynamodb_table.main.name
}

output "table_arn" {
  value = aws_dynamodb_table.main.arn
}

output "table_stream_arn" {
  value = aws_dynamodb_table.main.stream_arn
}

output "redis_url" {
  description = "URL de conexión con TLS (rediss://) al endpoint primario."
  value       = format("rediss://%s:%d/0", aws_elasticache_replication_group.redis.primary_endpoint_address, aws_elasticache_replication_group.redis.port)
}
