# ALB público (HTTP: sin dominio ni certificado ACM en Academy) → tareas en subnets privadas.
# Es la puerta de entrada pública de la API: tiene que ser internet-facing.
#tfsec:ignore:aws-elb-alb-not-public
resource "aws_lb" "api" {
  name                       = "${var.name_prefix}-alb"
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = var.public_subnet_ids
  security_groups            = [var.alb_security_group_id]
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "api" {
  # name_prefix (máx. 6 caracteres) para que create_before_destroy no choque de nombre.
  name_prefix          = "api-"
  port                 = var.api_port
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = var.vpc_id
  deregistration_delay = 30

  # /health responde 200 aunque Redis u OpenSearch estén caídos: una dependencia degradada
  # no saca a la tarea de rotación.
  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Sin dominio propio no hay certificado ACM que validar en Academy: el listener queda en HTTP.
#tfsec:ignore:aws-elb-http-not-used
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
