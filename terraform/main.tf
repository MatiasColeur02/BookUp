locals {
  api_port = 8000

  # Entorno común a la API y al indexador (el mismo código, api/app/config.py).
  # AWS_REGION no va acá: en Lambda es una variable reservada que el runtime ya define.
  shared_environment = {
    DYNAMO_TABLE     = module.database.table_name
    OPENSEARCH_URL   = module.database.opensearch_url
    OPENSEARCH_INDEX = "${var.project}-books"
    REDIS_URL        = module.database.redis_url
  }

  api_environment = merge(local.shared_environment, {
    AWS_REGION            = var.aws_region
    AUTH_MODE             = "cognito"
    COGNITO_REGION        = var.aws_region
    COGNITO_USER_POOL_ID  = module.auth.user_pool_id
    COGNITO_APP_CLIENT_ID = module.auth.client_id
    CORS_ORIGINS          = jsonencode([module.storage.frontend_url])
    S3_BUCKET             = module.storage.covers_bucket
    S3_REGION             = var.aws_region
  })
}

module "network" {
  source = "./modules/network"

  name_prefix        = local.name_prefix
  region             = var.aws_region
  vpc_cidr           = var.vpc_cidr
  azs                = local.azs
  single_nat_gateway = var.single_nat_gateway
  api_port           = local.api_port
}

module "storage" {
  source = "./modules/storage"

  name_prefix   = local.name_prefix
  suffix        = local.suffix
  force_destroy = var.force_destroy_buckets
}

module "database" {
  source = "./modules/database"

  name_prefix                           = local.name_prefix
  region                                = var.aws_region
  account_id                            = data.aws_caller_identity.current.account_id
  subnet_ids                            = module.network.database_subnet_ids
  redis_security_group_id               = module.network.security_group_ids["redis"]
  opensearch_security_group_id          = module.network.security_group_ids["opensearch"]
  dynamodb_pitr                         = var.dynamodb_pitr
  redis_node_type                       = var.redis_node_type
  redis_replicas                        = var.redis_replicas
  opensearch_instance_type              = var.opensearch_instance_type
  opensearch_volume_size                = var.opensearch_volume_size
  create_opensearch_service_linked_role = var.create_opensearch_service_linked_role
}

# Un solo zip de api/ para las dos Lambdas que reutilizan su código.
module "api_package" {
  source = "./modules/lambda_package"

  name       = "api-lambda"
  source_dir = local.api_source_dir
}

module "auth" {
  source = "./modules/auth"

  name_prefix          = local.name_prefix
  suffix               = local.suffix
  region               = var.aws_region
  lambda_role_arn      = data.aws_iam_role.lab.arn
  frontend_url         = module.storage.frontend_url
  bridge_source_dir    = "${local.repo_root}/auth-bridge"
  api_package_zip      = module.api_package.zip_path
  api_package_hash     = module.api_package.zip_hash
  table_name           = module.database.table_name
  access_token_minutes = var.access_token_minutes
  log_retention_days   = var.log_retention_days
}

module "indexer" {
  source = "./modules/indexer"

  name_prefix        = local.name_prefix
  lambda_role_arn    = data.aws_iam_role.lab.arn
  package_zip        = module.api_package.zip_path
  package_hash       = module.api_package.zip_hash
  stream_arn         = module.database.table_stream_arn
  subnet_ids         = module.network.private_subnet_ids
  security_group_id  = module.network.security_group_ids["lambda"]
  environment        = local.shared_environment
  log_retention_days = var.log_retention_days
}

module "compute" {
  source = "./modules/compute"

  name_prefix           = local.name_prefix
  region                = var.aws_region
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  alb_security_group_id = module.network.security_group_ids["alb"]
  app_security_group_id = module.network.security_group_ids["app"]
  task_role_arn         = data.aws_iam_role.lab.arn
  api_source_dir        = local.api_source_dir
  api_port              = local.api_port
  cpu                   = var.api_cpu
  memory                = var.api_memory
  cpu_architecture      = var.api_cpu_architecture
  desired_count         = var.api_desired_count
  environment           = local.api_environment
  log_retention_days    = var.log_retention_days
  run_seed              = var.run_seed
  seed_trigger          = module.database.table_arn
}
