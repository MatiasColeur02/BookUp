output "url" {
  description = "URL interna de OpenSearch (HTTP, a través del NLB)."
  value       = "http://${aws_lb.search.dns_name}:${var.port}"

  # Quien use la URL espera a que el servicio esté sano, no solo a que exista el NLB.
  depends_on = [aws_ecs_service.search]
}
