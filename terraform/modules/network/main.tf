# VPC de tres capas sobre el módulo externo terraform-aws-modules/vpc:
#   public   → ALB y NAT Gateway(s)
#   private  → tareas de ECS y la Lambda indexadora (salen a Internet por el NAT)
#   database → ElastiCache y OpenSearch (sin ruta a Internet)
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name = "${var.name_prefix}-vpc"
  cidr = var.vpc_cidr
  azs  = var.azs

  # 10.0.1.0/24, 10.0.2.0/24 · 10.0.11.0/24, 10.0.12.0/24 · 10.0.21.0/24, 10.0.22.0/24
  public_subnets   = [for i, _ in var.azs : cidrsubnet(var.vpc_cidr, 8, i + 1)]
  private_subnets  = [for i, _ in var.azs : cidrsubnet(var.vpc_cidr, 8, i + 11)]
  database_subnets = [for i, _ in var.azs : cidrsubnet(var.vpc_cidr, 8, i + 21)]

  public_subnet_names   = [for az in var.azs : "${var.name_prefix}-public-${substr(az, -2, 2)}"]
  private_subnet_names  = [for az in var.azs : "${var.name_prefix}-app-${substr(az, -2, 2)}"]
  database_subnet_names = [for az in var.azs : "${var.name_prefix}-data-${substr(az, -2, 2)}"]

  enable_nat_gateway     = true
  single_nat_gateway     = var.single_nat_gateway
  one_nat_gateway_per_az = !var.single_nat_gateway

  # Los subnet groups de ElastiCache se arman en el módulo de datos; el de RDS no se usa.
  create_database_subnet_group       = false
  create_database_subnet_route_table = true

  enable_dns_hostnames = true
  enable_dns_support   = true
}

# Gateway endpoints (gratis): el tráfico de la API y de la Lambda hacia S3 y DynamoDB no
# pasa por el NAT.
resource "aws_vpc_endpoint" "gateway" {
  for_each = toset(["s3", "dynamodb"])

  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids

  tags = { Name = "${var.name_prefix}-${each.key}-endpoint" }
}
