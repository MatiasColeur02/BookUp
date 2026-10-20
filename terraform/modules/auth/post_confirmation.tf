# Trigger Post Confirmation: al confirmar un registro crea el User (customer) en DynamoDB.
# Fuera de VPC: llega a DynamoDB por el endpoint público.
resource "aws_cloudwatch_log_group" "post_confirmation" {
  name              = "/aws/lambda/${var.name_prefix}-post-confirmation"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "post_confirmation" {
  function_name    = "${var.name_prefix}-post-confirmation"
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = "app.cognito_triggers.post_confirmation"
  filename         = var.api_package_zip
  source_code_hash = var.api_package_hash
  # Cognito espera ~5 s y reintenta; el handler es idempotente.
  timeout     = 5
  memory_size = 512

  environment {
    variables = {
      DYNAMO_TABLE = var.table_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.post_confirmation]
}

# En la consola se agrega solo al asociar el trigger; sin él, todo registro falla.
resource "aws_lambda_permission" "cognito_post_confirmation" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.post_confirmation.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.this.arn
}
