output "api_url" {
  value = "http://${aws_lb.api.dns_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "image_uri" {
  value = local.image_uri
}

output "reindex_command" {
  description = "Reconstruye el índice de OpenSearch desde DynamoDB (p. ej. si la tarea de búsqueda se reemplazó)."
  value = join(" ", [
    "aws ecs run-task --region ${var.region} --cluster ${var.cluster_name}",
    "--task-definition ${aws_ecs_task_definition.api.family} --launch-type FARGATE",
    "--network-configuration '${local.network_config}'",
    "--overrides '${local.one_shot_overrides.reindex}'",
  ])
}

output "service_name" {
  value = aws_ecs_service.api.name
}
