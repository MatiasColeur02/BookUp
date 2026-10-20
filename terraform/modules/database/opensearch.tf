# Un dominio en VPC sin el service-linked role falla. En la consola se crea solo; por API hay
# que crearlo, salvo que la cuenta ya lo tenga (si existe, crearlo de nuevo da error).
resource "aws_iam_service_linked_role" "opensearch" {
  count = var.create_opensearch_service_linked_role ? 1 : 0

  aws_service_name = "opensearchservice.amazonaws.com"
}

# Proyección de solo lectura del catálogo (la fuente de verdad es DynamoDB). Un nodo en una
# subnet de datos. Sin fine-grained access control: lo protege el security group, por eso el
# cliente de la API no necesita firmar con SigV4.
resource "aws_opensearch_domain" "search" {
  domain_name    = "${var.name_prefix}-search"
  engine_version = "OpenSearch_2.17"

  cluster_config {
    instance_type          = var.opensearch_instance_type
    instance_count         = 1
    zone_awareness_enabled = false
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp2"
    volume_size = var.opensearch_volume_size
  }

  vpc_options {
    subnet_ids         = [var.subnet_ids[0]]
    security_group_ids = [var.opensearch_security_group_id]
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "*" }
      Action    = "es:ESHttp*"
      Resource  = "arn:aws:es:${var.region}:${var.account_id}:domain/${var.name_prefix}-search/*"
    }]
  })

  depends_on = [aws_iam_service_linked_role.opensearch]
}
