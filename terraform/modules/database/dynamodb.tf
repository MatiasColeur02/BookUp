# Tabla única. Tiene que coincidir con api/app/persistence/table.py: el seed llama a
# ensure_table(), que falla si la clave o los GSIs son otros.
locals {
  gsis = {
    GSI1 = ["GSI1PK", "GSI1SK"] # listados ordenados
    GSI2 = ["GSI2PK", "GSI2SK"] # hijos de X
    GSI3 = ["GSI3PK", "GSI3SK"] # por sede
    GSI4 = ["GSI4PK", "GSI4SK"] # reservas abiertas (disperso)
  }

  dynamo_attributes = distinct(concat(["PK", "SK"], flatten(values(local.gsis))))
}

resource "aws_dynamodb_table" "main" {
  name         = var.name_prefix
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  dynamic "attribute" {
    for_each = local.dynamo_attributes
    content {
      name = attribute.value
      type = "S"
    }
  }

  dynamic "global_secondary_index" {
    for_each = local.gsis
    content {
      name            = global_secondary_index.key
      projection_type = "ALL"

      key_schema {
        attribute_name = global_secondary_index.value[0]
        key_type       = "HASH"
      }

      key_schema {
        attribute_name = global_secondary_index.value[1]
        key_type       = "RANGE"
      }
    }
  }

  # Alimenta a la Lambda indexadora de OpenSearch.
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = var.dynamodb_pitr
  }

  server_side_encryption {
    enabled = true
  }
}
