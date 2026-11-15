<!-- BEGIN_TF_DOCS -->
## Requirements

No requirements.

## Providers

| Name | Version |
| ---- | ------- |
| <a name="provider_aws"></a> [aws](#provider\_aws) | n/a |

## Modules

No modules.

## Resources

| Name | Type |
| ---- | ---- |
| [aws_cloudwatch_event_rule.deadline_scan](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_rule) | resource |
| [aws_cloudwatch_event_target.deadline_scan](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_target) | resource |
| [aws_cloudwatch_log_group.this](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_lambda_event_source_mapping.notifier](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_event_source_mapping) | resource |
| [aws_lambda_function.this](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_permission.events_deadline_scanner](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_lambda_permission.sns_inbox_writer](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_sns_topic.reservation_events](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic) | resource |
| [aws_sns_topic_subscription.inbox_writer](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic_subscription) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_deadline_scan_minutes"></a> [deadline\_scan\_minutes](#input\_deadline\_scan\_minutes) | Cada cuántos minutos corre el job de vencimientos. | `number` | `15` | no |
| <a name="input_lambda_role_arn"></a> [lambda\_role\_arn](#input\_lambda\_role\_arn) | Rol de las tres Lambdas (LabRole: el Learner Lab no deja crear roles). | `string` | n/a | yes |
| <a name="input_log_retention_days"></a> [log\_retention\_days](#input\_log\_retention\_days) | n/a | `number` | n/a | yes |
| <a name="input_name_prefix"></a> [name\_prefix](#input\_name\_prefix) | n/a | `string` | n/a | yes |
| <a name="input_package_hash"></a> [package\_hash](#input\_package\_hash) | n/a | `string` | n/a | yes |
| <a name="input_package_zip"></a> [package\_zip](#input\_package\_zip) | Zip de api/ (el mismo que usan el indexador y el trigger de Cognito). | `string` | n/a | yes |
| <a name="input_retention_days"></a> [retention\_days](#input\_retention\_days) | Días que vive una notificación en la bandeja (TTL de DynamoDB sobre ttl\_epoch). | `number` | `90` | no |
| <a name="input_table_name"></a> [table\_name](#input\_table\_name) | n/a | `string` | n/a | yes |
| <a name="input_table_stream_arn"></a> [table\_stream\_arn](#input\_table\_stream\_arn) | Stream de la tabla (NEW\_AND\_OLD\_IMAGES). El notificador es su segundo lector. | `string` | n/a | yes |
| <a name="input_timezone"></a> [timezone](#input\_timezone) | Zona horaria de las fechas del texto de las notificaciones. | `string` | `"America/Argentina/Buenos_Aires"` | no |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_function_names"></a> [function\_names](#output\_function\_names) | Nombre de cada Lambda, por rol (notifier, inbox-writer, deadline-scanner). |
| <a name="output_schedule_rule"></a> [schedule\_rule](#output\_schedule\_rule) | Rule de EventBridge que dispara el job de vencimientos. |
| <a name="output_topic_arn"></a> [topic\_arn](#output\_topic\_arn) | Topic SNS de los eventos de reservas (para suscribir canales nuevos). |
<!-- END_TF_DOCS -->
