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

  # Auto-registro de lectores en la Hosted UI.
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

resource "aws_cognito_user_pool_domain" "this" {
  domain       = "${var.name_prefix}-${var.suffix}"
  user_pool_id = aws_cognito_user_pool.this.id
}

# Cliente confidencial: el secreto lo conoce solo la Lambda puente.
resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = [local.callback_url]
  logout_urls   = [local.signed_out_url]

  explicit_auth_flows = ["ALLOW_REFRESH_TOKEN_AUTH"]

  access_token_validity  = var.access_token_minutes
  id_token_validity      = var.access_token_minutes
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"
}

locals {
  cognito_domain = "${aws_cognito_user_pool_domain.this.domain}.auth.${var.region}.amazoncognito.com"
}
