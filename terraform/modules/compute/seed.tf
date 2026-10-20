# Datos de demo: una tarea de Fargate one-shot con la misma imagen y el mismo entorno que la
# API, que corre app.seed (DynamoDB + reindexado de OpenSearch) y app.seed_cognito (cuentas
# en el User Pool). Los dos son idempotentes. Se vuelve a correr solo si cambia seed_trigger.
resource "terraform_data" "seed" {
  count = var.run_seed ? 1 : 0

  triggers_replace = [var.seed_trigger]

  provisioner "local-exec" {
    command = "${path.module}/run_seed.sh"
    environment = {
      REGION          = var.region
      CLUSTER         = aws_ecs_cluster.this.name
      TASK_DEFINITION = aws_ecs_task_definition.api.arn
      NETWORK_CONFIG = jsonencode({
        awsvpcConfiguration = {
          subnets        = var.private_subnet_ids
          securityGroups = [var.app_security_group_id]
          assignPublicIp = "DISABLED"
        }
      })
      OVERRIDES = jsonencode({
        containerOverrides = [{
          name    = local.container_name
          command = ["sh", "-c", "python -m app.seed && python -m app.seed_cognito"]
        }]
      })
    }
  }

  depends_on = [aws_ecs_service.api]
}
