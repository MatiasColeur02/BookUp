# Identidad. Cognito solo resuelve quién es el usuario (sub + email); rol y sede viven en el
# ítem User de DynamoDB (COGNITO_ROADMAP.md §0).
resource "aws_cognito_user_pool" "this" {
  name                = "${var.name_prefix}-users"
  deletion_protection = "INACTIVE"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  username_configuration {
    case_sensitive = false
  }

  # Auto-registro de lectores (`SignUp` desde el formulario del frontend).
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  # Mínimo 8, sin clases obligatorias: la regla del frontend y la que deja usar bookup123.
  password_policy {
    minimum_length                   = 8
    require_lowercase                = false
    require_uppercase                = false
    require_numbers                  = false
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  mfa_configuration = "OFF"

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Sin SES en Academy: remitente default de Cognito (cuota baja).
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  dynamic "schema" {
    for_each = toset(["email", "name"])
    content {
      name                = schema.value
      attribute_data_type = "String"
      required            = true
      mutable             = true

      string_attribute_constraints {
        min_length = 1
        max_length = 2048
      }
    }
  }

  lambda_config {
    post_confirmation = aws_lambda_function.post_confirmation.arn
  }

  lifecycle {
    # Cognito no deja modificar el schema de un pool existente: un cambio lo recrearía y
    # borraría todas las cuentas.
    ignore_changes = [schema]
  }
}

# Cliente público: el frontend (los formularios propios, `frontend/src/lib/auth.ts`) llama
# directo a la API del User Pool. Sin secret, porque en el browser no se puede guardar uno.
# Sin Hosted UI ni OAuth: no hay dominio, callbacks ni puente HTTPS.
#
# USER_PASSWORD_AUTH y no SRP: el frontend es HTTP (website de S3) y las implementaciones de
# SRP necesitan `crypto.subtle`, que el browser solo da en contextos seguros. La contraseña
# viaja igual por TLS, porque el endpoint de Cognito es HTTPS.
resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  access_token_validity  = var.access_token_minutes
  id_token_validity      = var.access_token_minutes
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  enable_token_revocation = true
  # Login y «olvidé mi contraseña» contestan igual exista o no la cuenta.
  prevent_user_existence_errors = "ENABLED"
}
