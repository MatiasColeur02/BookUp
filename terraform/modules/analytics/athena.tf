locals {
  # Glue/Athena no aceptan guiones en los nombres de base ni de tabla.
  database_name = "${replace(var.name_prefix, "-", "_")}_analytics"

  # Una tabla externa por archivo que escribe el exportador (app/analytics/exporter.py). Las
  # columnas tienen que coincidir con las claves de las filas JSON.
  tables = {
    reservations = {
      location = "reservations"
      columns = {
        reservation_id   = "bigint"
        user_id          = "bigint"
        physical_book_id = "bigint"
        isbn             = "string"
        library_id       = "bigint"
        library_name     = "string"
        library_city     = "string"
        library_state    = "string"
        status           = "string"
        picked_up        = "boolean"
        reserved_month   = "string"
        reserved_at      = "string"
        expires_at       = "string"
        picked_up_at     = "string"
        returned_at      = "string"
        cancelled_at     = "string"
        cancelled_by     = "string"
      }
    }
    libraries = {
      location = "libraries"
      columns = {
        library_id = "bigint"
        name       = "string"
        city       = "string"
        state      = "string"
      }
    }
    books = {
      location = "books"
      columns = {
        isbn     = "string"
        title    = "string"
        language = "string"
        pages    = "int"
      }
    }
  }

  # Reportes listos para correr en la consola de Athena (workgroup del proyecto).
  queries = {
    "1-reservas-por-sede-y-mes" = {
      description = "Reservas por sede y por mes (el reporte del TP1)."
      sql         = <<-SQL
        SELECT library_name AS sede,
               reserved_month AS mes,
               count(*) AS reservas
        FROM reservations
        GROUP BY library_name, reserved_month
        ORDER BY reserved_month DESC, reservas DESC
      SQL
    }
    "2-libros-mas-reservados" = {
      description = "Los 10 libros más reservados de toda la red."
      sql         = <<-SQL
        SELECT b.title AS titulo,
               r.isbn,
               count(*) AS reservas
        FROM reservations r
        JOIN books b ON b.isbn = r.isbn
        GROUP BY b.title, r.isbn
        ORDER BY reservas DESC
        LIMIT 10
      SQL
    }
    "3-resultado-de-reservas-por-sede" = {
      description = "Cómo terminan las reservas de cada sede: devueltas, canceladas, vencidas, perdidas y abiertas."
      sql         = <<-SQL
        SELECT library_name AS sede,
               count(*) AS total,
               count_if(status = 'returned') AS devueltas,
               count_if(status = 'cancelled') AS canceladas,
               count_if(status = 'expired') AS vencidas,
               count_if(status = 'lost') AS perdidas,
               count_if(status IN ('reserved', 'loaned')) AS abiertas,
               round(100.0 * count_if(status IN ('cancelled', 'expired')) / count(*), 1) AS pct_no_retiradas
        FROM reservations
        GROUP BY library_name
        ORDER BY total DESC
      SQL
    }
    "4-reservas-por-ciudad" = {
      description = "Demanda por ciudad y provincia."
      sql         = <<-SQL
        SELECT library_state AS provincia,
               library_city AS ciudad,
               count(*) AS reservas
        FROM reservations
        GROUP BY library_state, library_city
        ORDER BY reservas DESC
      SQL
    }
  }
}

resource "aws_glue_catalog_database" "analytics" {
  name        = local.database_name
  description = "Foto de los datos de BookUp para reportes (la escribe la Lambda exportadora)"
}

resource "aws_glue_catalog_table" "this" {
  for_each = local.tables

  database_name = aws_glue_catalog_database.analytics.name
  name          = each.key
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL       = "TRUE"
    classification = "json"
  }

  storage_descriptor {
    location      = "s3://${terraform_data.bucket.output.name}/${each.value.location}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      # Una fila JSON por línea; una clave ausente es NULL.
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    dynamic "columns" {
      for_each = each.value.columns
      content {
        name = columns.key
        type = columns.value
      }
    }
  }
}

# Workgroup propio: separa los resultados y los costos de BookUp del resto, fuerza la ubicación
# de los resultados y corta las queries que escanean de más (el lab tiene presupuesto).
resource "aws_athena_workgroup" "this" {
  name          = "${var.name_prefix}-analytics"
  description   = "Reportes de BookUp"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    result_configuration {
      output_location = "s3://${terraform_data.bucket.output.name}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

resource "aws_athena_named_query" "this" {
  for_each = local.queries

  name        = each.key
  description = each.value.description
  workgroup   = aws_athena_workgroup.this.id
  database    = aws_glue_catalog_database.analytics.name
  query       = each.value.sql
}
