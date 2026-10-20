# OpenSearch como contenedor en Fargate: el Learner Lab no permite dominios gestionados
# (es:CreateDomain denegado) ni Cloud Map, así que la dirección estable la da un NLB interno.
# Misma imagen y misma configuración que el servicio `search` del docker-compose.
#
# El índice vive en el disco efímero de la tarea: si la tarea se reemplaza, arranca vacío y se
# reconstruye con `app.reindex` (output reindex_command). La fuente de verdad es DynamoDB.
resource "aws_lb" "search" {
  name               = "${var.name_prefix}-search-nlb"
  load_balancer_type = "network"
  internal           = true
  subnets            = var.subnet_ids
  security_groups    = [var.nlb_security_group_id]

  enable_cross_zone_load_balancing = true
}

resource "aws_lb_target_group" "search" {
  name_prefix          = "srch-"
  port                 = var.port
  protocol             = "TCP"
  target_type          = "ip"
  vpc_id               = var.vpc_id
  deregistration_delay = 10

  # yellow es lo mejor que alcanza un nodo único (réplicas sin asignar) y responde 200.
  health_check {
    protocol            = "HTTP"
    path                = "/_cluster/health"
    matcher             = "200"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener" "search" {
  load_balancer_arn = aws_lb.search.arn
  port              = var.port
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.search.arn
  }
}

resource "aws_cloudwatch_log_group" "search" {
  name              = "/ecs/${var.name_prefix}-search"
  retention_in_days = var.log_retention_days
}

locals {
  heap_mb = floor(var.memory / 2)

  opensearch_environment = {
    "discovery.type"                                    = "single-node"
    DISABLE_SECURITY_PLUGIN                             = "true"
    DISABLE_INSTALL_DEMO_CONFIG                         = "true"
    OPENSEARCH_JAVA_OPTS                                = "-Xms${local.heap_mb}m -Xmx${local.heap_mb}m"
    "bootstrap.memory_lock"                             = "false"
    "cluster.routing.allocation.disk.threshold_enabled" = "false"
  }
}

resource "aws_ecs_task_definition" "search" {
  family                   = "${var.name_prefix}-search"
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
    name      = "opensearch"
    image     = var.image
    essential = true

    portMappings = [{ containerPort = var.port, protocol = "tcp" }]
    environment  = [for name, value in local.opensearch_environment : { name = name, value = value }]
    ulimits      = [{ name = "nofile", softLimit = 65536, hardLimit = 65536 }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.search.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "opensearch"
      }
    }
  }])
}

resource "aws_ecs_service" "search" {
  name            = "${var.name_prefix}-search"
  cluster         = var.cluster_id
  task_definition = aws_ecs_task_definition.search.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  # Nodo único: el reemplazo baja el viejo antes de subir el nuevo (dos nodos sueltos con
  # índices distintos detrás del mismo NLB devolverían resultados alternados).
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  health_check_grace_period_seconds  = 180

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.task_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.search.arn
    container_name   = "opensearch"
    container_port   = var.port
  }

  # El apply espera a que OpenSearch esté sano: la API, el indexador y el seed lo necesitan.
  wait_for_steady_state = true

  depends_on = [aws_lb_listener.search]
}
