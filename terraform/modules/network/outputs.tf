output "vpc_id" {
  value = module.vpc.vpc_id
}

output "public_subnet_ids" {
  value = module.vpc.public_subnets
}

output "private_subnet_ids" {
  value = module.vpc.private_subnets
}

output "database_subnet_ids" {
  value = module.vpc.database_subnets
}

output "security_group_ids" {
  description = "Mapa componente → id del security group (alb, app, lambda, redis, search_nlb, search)."
  value       = { for name, sg in aws_security_group.this : name => sg.id }
}
