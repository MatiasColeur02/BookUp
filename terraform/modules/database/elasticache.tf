resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.name_prefix}-redis-subnet-group"
  subnet_ids = var.subnet_ids
}

# Primario + réplicas en zonas distintas. Con cifrado en tránsito la URL es rediss://.
# El parameter group default.redis7 trae maxmemory-policy=volatile-lru, que es lo que pide
# la invalidación por generaciones de api/app/cache.py.
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "Cache de lecturas y rate limiting de la API"

  engine               = "redis"
  engine_version       = "7.1"
  parameter_group_name = "default.redis7"
  node_type            = var.redis_node_type
  port                 = 6379

  num_cache_clusters         = var.redis_replicas + 1
  automatic_failover_enabled = var.redis_replicas > 0
  multi_az_enabled           = var.redis_replicas > 0

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [var.redis_security_group_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  apply_immediately = true
}
