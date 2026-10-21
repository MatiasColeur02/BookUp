<!-- BEGIN_TF_DOCS -->
## Requirements

No requirements.

## Providers

| Name | Version |
| ---- | ------- |
| <a name="provider_archive"></a> [archive](#provider\_archive) | n/a |
| <a name="provider_terraform"></a> [terraform](#provider\_terraform) | n/a |

## Modules

No modules.

## Resources

| Name | Type |
| ---- | ---- |
| [terraform_data.build](https://registry.terraform.io/providers/hashicorp/terraform/latest/docs/resources/data) | resource |
| [archive_file.this](https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/file) | data source |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_name"></a> [name](#input\_name) | Nombre del paquete (directorio y zip en terraform/.build/). | `string` | n/a | yes |
| <a name="input_python_version"></a> [python\_version](#input\_python\_version) | Versión de Python del runtime de Lambda, para elegir los wheels. | `string` | `"3.12"` | no |
| <a name="input_source_dir"></a> [source\_dir](#input\_source\_dir) | Directorio con app/ y requirements.txt. | `string` | n/a | yes |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_zip_hash"></a> [zip\_hash](#output\_zip\_hash) | n/a |
| <a name="output_zip_path"></a> [zip\_path](#output\_zip\_path) | n/a |
<!-- END_TF_DOCS -->