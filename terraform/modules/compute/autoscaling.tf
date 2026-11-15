# Autoscaling del servicio de la API (elasticidad).
#
# El servicio arranca con `desired_count` tareas y desde ahí Application Auto Scaling
# mueve ese número entre `autoscaling_min_capacity` y `autoscaling_max_capacity` para
# mantener la CPU promedio del servicio cerca de `autoscaling_cpu_target` (target tracking:
# funciona como un termostato).
#
# No se pasa `role_arn`: Application Auto Scaling usa su service-linked role
# (AWSServiceRoleForApplicationAutoScaling_ECSService), que no es un rol propio.

# 1) Qué se escala y entre qué límites.
resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${var.cluster_name}/${aws_ecs_service.api.name}"
  min_capacity       = var.autoscaling_min_capacity
  max_capacity       = var.autoscaling_max_capacity
}

# 2) La regla: mantener la CPU promedio del servicio cerca del objetivo.
resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${var.name_prefix}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  resource_id        = aws_appautoscaling_target.api.resource_id

  target_tracking_scaling_policy_configuration {
    target_value = var.autoscaling_cpu_target

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    # Sube rápido ante un pico; baja más despacio para no sacar tareas que se vuelvan a
    # necesitar enseguida (evita que el servicio "rebote").
    scale_out_cooldown = 60
    scale_in_cooldown  = 120
  }
}
