locals {
  # Un security group por componente. Las reglas de entrada se declaran abajo, por nombre,
  # para que una regla pueda referenciar a otro grupo sin ciclos.
  security_groups = {
    alb        = "Entrada HTTP publica al ALB"
    app        = "Tareas de ECS de la API"
    lambda     = "Lambda indexadora"
    redis      = "ElastiCache Redis"
    opensearch = "Dominio de OpenSearch"
  }

  ingress_rules = {
    alb_http = {
      sg = "alb", port = 80, cidr = "0.0.0.0/0", source = null
    }
    app_from_alb = {
      sg = "app", port = var.api_port, cidr = null, source = "alb"
    }
    redis_from_app = {
      sg = "redis", port = 6379, cidr = null, source = "app"
    }
    redis_from_lambda = {
      sg = "redis", port = 6379, cidr = null, source = "lambda"
    }
    opensearch_from_app = {
      sg = "opensearch", port = 443, cidr = null, source = "app"
    }
    opensearch_from_lambda = {
      sg = "opensearch", port = 443, cidr = null, source = "lambda"
    }
  }

  # Solo los que inician conexiones necesitan salida.
  egress_groups = toset(["alb", "app", "lambda"])
}

resource "aws_security_group" "this" {
  for_each = local.security_groups

  # name_prefix y no name: create_before_destroy necesita que el reemplazo tenga otro nombre.
  name_prefix = "${var.name_prefix}-${each.key}-"
  description = each.value
  vpc_id      = module.vpc.vpc_id

  tags = { Name = "${var.name_prefix}-${each.key}-sg" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "this" {
  for_each = local.ingress_rules

  security_group_id            = aws_security_group.this[each.value.sg].id
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
  cidr_ipv4                    = each.value.cidr
  referenced_security_group_id = each.value.source == null ? null : aws_security_group.this[each.value.source].id
  description                  = replace(each.key, "_", " ")
}

resource "aws_vpc_security_group_egress_rule" "all" {
  for_each = local.egress_groups

  security_group_id = aws_security_group.this[each.key].id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "all outbound"
}
