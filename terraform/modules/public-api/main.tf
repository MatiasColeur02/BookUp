# API pública gobernada (public-api/): un API Gateway REST delante del catálogo, para que
# otras bibliotecas consulten los libros con una API key propia y un límite de uso por cliente.
#
# Por qué REST (v1) y no HTTP (v2, como el auth-bridge): las API keys + usage plans
# (throttling y quota por cliente) solo existen en REST API. El HTTP API del puente de Cognito
# confirma que el Learner Lab deja crear API Gateway; acá usamos la variante que trae gobierno.
#
# Integración: HTTP_PROXY directo al ALB (internet-facing, HTTP:80). No hace falta VPC link
# (eso pediría un NLB); el ALB ya es público. Solo se exponen los GET de lectura del catálogo.

resource "aws_api_gateway_rest_api" "public" {
  name        = "${var.name_prefix}-public-api"
  description = "Catálogo público de BookUp para consumidores externos (solo lectura)."

  # REGIONAL evita la distribución de CloudFront de EDGE (más lenta de crear y de propagar),
  # que además obliga a us-east-1. Para el lab y la demo, regional alcanza.
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# --- Árbol de recursos -------------------------------------------------------
# /books, y debajo los hijos estáticos (search, cities) y el variable {isbn} con su availability.
# API Gateway resuelve primero los tramos estáticos, así que search/cities no chocan con {isbn}.

resource "aws_api_gateway_resource" "books" {
  rest_api_id = aws_api_gateway_rest_api.public.id
  parent_id   = aws_api_gateway_rest_api.public.root_resource_id
  path_part   = "books"
}

resource "aws_api_gateway_resource" "search" {
  rest_api_id = aws_api_gateway_rest_api.public.id
  parent_id   = aws_api_gateway_resource.books.id
  path_part   = "search"
}

resource "aws_api_gateway_resource" "cities" {
  rest_api_id = aws_api_gateway_rest_api.public.id
  parent_id   = aws_api_gateway_resource.books.id
  path_part   = "cities"
}

resource "aws_api_gateway_resource" "isbn" {
  rest_api_id = aws_api_gateway_rest_api.public.id
  parent_id   = aws_api_gateway_resource.books.id
  path_part   = "{isbn}"
}

resource "aws_api_gateway_resource" "availability" {
  rest_api_id = aws_api_gateway_rest_api.public.id
  parent_id   = aws_api_gateway_resource.isbn.id
  path_part   = "availability"
}

locals {
  # Cada endpoint de lectura: el recurso donde cuelga, el path real contra el backend, y qué
  # parámetros de path hay que declarar y reenviar (el proxy ya pasa solo el query string).
  endpoints = {
    list = {
      resource_id = aws_api_gateway_resource.books.id
      path        = "books"
      path_params = []
    }
    search = {
      resource_id = aws_api_gateway_resource.search.id
      path        = "books/search"
      path_params = []
    }
    cities = {
      resource_id = aws_api_gateway_resource.cities.id
      path        = "books/cities"
      path_params = []
    }
    detail = {
      resource_id = aws_api_gateway_resource.isbn.id
      path        = "books/{isbn}"
      path_params = ["isbn"]
    }
    availability = {
      resource_id = aws_api_gateway_resource.availability.id
      path        = "books/{isbn}/availability"
      path_params = ["isbn"]
    }
  }
}

# --- Métodos e integraciones -------------------------------------------------

# Cada GET pide API key (api_key_required): sin una clave válida ligada al usage plan, 403.
# authorization = NONE porque el gobierno es por API key, no por usuario (es catálogo público).
resource "aws_api_gateway_method" "get" {
  for_each = local.endpoints

  rest_api_id      = aws_api_gateway_rest_api.public.id
  resource_id      = each.value.resource_id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = true

  request_parameters = {
    for p in each.value.path_params : "method.request.path.${p}" => true
  }
}

# HTTP_PROXY al ALB: reenvía método, headers y query string tal cual; los path params hay que
# mapearlos explícitamente (lo único que el proxy no infiere).
resource "aws_api_gateway_integration" "proxy" {
  for_each = local.endpoints

  rest_api_id             = aws_api_gateway_rest_api.public.id
  resource_id             = each.value.resource_id
  http_method             = aws_api_gateway_method.get[each.key].http_method
  type                    = "HTTP_PROXY"
  integration_http_method = "GET"
  uri                     = "${var.backend_base_url}/${each.value.path}"
  connection_type         = "INTERNET"
  timeout_milliseconds    = 29000

  request_parameters = {
    for p in each.value.path_params :
    "integration.request.path.${p}" => "method.request.path.${p}"
  }
}

# --- Deploy y stage ----------------------------------------------------------

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.public.id

  # Redeploy cuando cambia algo de la superficie o el backend: sin esto, el stage sigue
  # sirviendo la versión vieja aunque el plan muestre cambios en métodos/integraciones.
  triggers = {
    redeployment = sha1(jsonencode([
      var.backend_base_url,
      [for k in sort(keys(local.endpoints)) : aws_api_gateway_method.get[k].id],
      [for k in sort(keys(local.endpoints)) : aws_api_gateway_integration.proxy[k].id],
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_api_gateway_integration.proxy]
}

resource "aws_api_gateway_stage" "public" {
  rest_api_id   = aws_api_gateway_rest_api.public.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.stage_name
}

# Métricas detalladas por método en CloudWatch (Count, Latency, 4XX/5XX por recurso) y el
# techo de throttling del stage. metrics_enabled NO necesita el rol de CloudWatch a nivel
# cuenta (eso solo lo piden los access/execution logs), así que levanta en el lab sin tocar
# configuración global.
resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.public.id
  stage_name  = aws_api_gateway_stage.public.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    throttling_rate_limit  = var.stage_throttle_rate_limit
    throttling_burst_limit = var.stage_throttle_burst_limit
  }
}

# --- Gobierno: API keys + usage plan ----------------------------------------
# Una clave por consumidor externo. El usage plan aplica throttling y quota POR CLAVE
# (cada API key lleva sus propios contadores), así un cliente ruidoso no afecta al resto.

resource "aws_api_gateway_api_key" "consumer" {
  for_each = toset(var.external_consumers)

  name        = "${var.name_prefix}-public-${each.key}"
  description = "Clave de consumo del catálogo público de BookUp (${each.key})."
  enabled     = true
}

resource "aws_api_gateway_usage_plan" "public" {
  name        = "${var.name_prefix}-public-plan"
  description = "Plan de consumo del catálogo público: límite por segundo y cuota mensual por cliente."

  api_stages {
    api_id = aws_api_gateway_rest_api.public.id
    stage  = aws_api_gateway_stage.public.stage_name
  }

  throttle_settings {
    rate_limit  = var.consumer_rate_limit
    burst_limit = var.consumer_burst_limit
  }

  quota_settings {
    limit  = var.consumer_quota_limit
    period = var.consumer_quota_period
  }
}

resource "aws_api_gateway_usage_plan_key" "consumer" {
  for_each = aws_api_gateway_api_key.consumer

  key_id        = each.value.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.public.id
}
