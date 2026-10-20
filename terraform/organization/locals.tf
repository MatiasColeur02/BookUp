resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  # Sufijo de los nombres globalmente únicos: el elegido o uno aleatorio estable.
  suffix      = lower(coalesce(var.name_suffix, random_id.suffix.hex))
  name_prefix = var.project

  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  repo_root      = abspath("${path.root}/../..")
  api_source_dir = "${local.repo_root}/api"
}
