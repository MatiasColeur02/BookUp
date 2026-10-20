resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days
}

locals {
  container_name = "api"
}

# Task role y execution role: LabRole (no se pueden crear roles). Las credenciales de AWS
# salen de ahí por la cadena default de boto3; nunca van en el entorno.
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.task_role_arn
  task_role_arn            = var.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }

  container_definitions = jsonencode([{
    name      = local.container_name
    image     = local.image_uri
    essential = true
    command   = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", tostring(var.api_port), "--proxy-headers", "--forwarded-allow-ips", "*"]

    portMappings = [{ containerPort = var.api_port, protocol = "tcp" }]

    environment = [for name, value in var.environment : { name = name, value = value }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "api"
      }
    }
  }])

  # La imagen tiene que estar en ECR antes de que una tarea intente bajarla.
  depends_on = [terraform_data.image]
}

resource "aws_ecs_service" "api" {
  name            = "${var.name_prefix}-api"
  cluster         = var.cluster_id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = local.container_name
    container_port   = var.api_port
  }

  # Un deploy que no levanta vuelve solo a la versión anterior.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # El target group tiene que estar asociado a un listener antes de crear el servicio.
  depends_on = [aws_lb_listener.http]
}
