# Puente HTTPS (auth-bridge/): Cognito solo acepta callbacks HTTPS y el frontend en S3 es
# HTTP. La Hosted UI vuelve a este API Gateway, la Lambda canjea el code por tokens con el
# client secret y redirige al frontend con el access token en el fragmento.
resource "aws_apigatewayv2_api" "bridge" {
  name          = "${var.name_prefix}-auth-bridge"
  protocol_type = "HTTP"
}

locals {
  callback_url   = "${aws_apigatewayv2_api.bridge.api_endpoint}/callback"
  signed_out_url = "${aws_apigatewayv2_api.bridge.api_endpoint}/signed-out"
  bridge_routes  = toset(["GET /callback", "GET /signed-out"])
}

data "archive_file" "bridge" {
  type        = "zip"
  source_file = "${var.bridge_source_dir}/handler.py"
  output_path = "${path.root}/.build/auth-bridge.zip"
}

resource "aws_cloudwatch_log_group" "bridge" {
  name              = "/aws/lambda/${var.name_prefix}-auth-bridge"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "bridge" {
  function_name    = "${var.name_prefix}-auth-bridge"
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.bridge.output_path
  source_code_hash = data.archive_file.bridge.output_base64sha256
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      COGNITO_DOMAIN        = local.cognito_domain
      COGNITO_CLIENT_ID     = aws_cognito_user_pool_client.web.id
      COGNITO_CLIENT_SECRET = aws_cognito_user_pool_client.web.client_secret
      CALLBACK_URL          = local.callback_url
      FRONTEND_URL          = var.frontend_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.bridge]
}

resource "aws_apigatewayv2_integration" "bridge" {
  api_id                 = aws_apigatewayv2_api.bridge.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.bridge.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "bridge" {
  for_each = local.bridge_routes

  api_id    = aws_apigatewayv2_api.bridge.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.bridge.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.bridge.id
  name        = "$default"
  auto_deploy = true

  # Nadie legítimo llama al callback más de una vez por login.
  default_route_settings {
    throttling_rate_limit  = 10
    throttling_burst_limit = 20
  }
}

resource "aws_lambda_permission" "apigw_bridge" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.bridge.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.bridge.execution_arn}/*/*"
}
