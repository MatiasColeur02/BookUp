# BookUp — Infraestructura como código (Terraform)

Despliega BookUp completo en una cuenta de AWS Academy (Learner Lab). Qué se crea y por qué:
[`../arquitectura-explain.md`](../arquitectura-explain.md).

## Estructura

```
terraform/
  versions.tf               # Terraform y providers (aws ~> 6.0, archive, random)
  providers.tf              # provider aws con default_tags
  variables.tf              # parámetros del despliegue (todos con default)
  locals.tf                 # sufijo único, AZs, tags, rutas del repo
  data.tf                   # LabRole, cuenta, AZs disponibles
  main.tf                   # composición de los módulos
  outputs.tf                # URLs, ids de Cognito y el .env del frontend
  terraform.tfvars.example
  modules/
    network/                # VPC (módulo externo), security groups, gateway endpoints
    storage/                # buckets S3 frontend y covers
    database/               # DynamoDB, ElastiCache Redis, OpenSearch
    lambda_package/         # build del zip de api/ para Lambda (build.sh)
    auth/                   # Cognito, Lambda post-confirmation, puente HTTPS (API Gateway + Lambda)
    indexer/                # Lambda indexadora + event source mapping + DLQ
    compute/                # ECR + push de la imagen, ALB, ECS Fargate, tarea del seed
```

## Módulos

| Módulo | Tipo | Recursos | Entradas principales → salidas |
|---|---|---|---|
| `terraform-aws-modules/vpc/aws` (`~> 6.0`) | **Externo** (Registry) | VPC, 6 subnets, IGW, NAT, route tables | CIDR, AZs → ids de subnets |
| `network` | Propio | Envuelve el módulo externo + 5 security groups + reglas + endpoints S3/DynamoDB | `vpc_cidr`, `azs`, `single_nat_gateway` → `vpc_id`, subnets, `security_group_ids` |
| `storage` | Propio | 2 buckets (ownership, cifrado, acceso público, policy), website, CORS | `suffix` → `frontend_url`, nombres de bucket |
| `database` | Propio | Tabla DynamoDB con 4 GSIs y stream, replication group de Redis, dominio de OpenSearch | subnets de datos, SGs → `table_name`, `table_stream_arn`, `redis_url`, `opensearch_url` |
| `lambda_package` | Propio, reutilizable | `terraform_data` que corre `build.sh` + `archive_file` | `source_dir` → `zip_path`, `zip_hash` |
| `auth` | Propio | User Pool, dominio, app client, 2 Lambdas, HTTP API con 2 rutas, permisos de invocación | `frontend_url`, zip de la API → `user_pool_id`, `client_id`, `cognito_domain`, URLs del puente |
| `indexer` | Propio | Lambda en VPC, SQS DLQ, event source mapping | zip, `stream_arn`, entorno → `dlq_url` |
| `compute` | Propio | ECR + lifecycle, push de la imagen, ALB/TG/listener, cluster, task definition, servicio, seed | subnets, SGs, entorno → `api_url`, `image_uri` |

`lambda_package` se usa una vez y su zip lo consumen dos módulos (`auth` e `indexer`), que
corren el mismo código de `api/`. El entorno común de la API y del indexador se arma una sola
vez en `main.tf` (`local.shared_environment`) y la API le agrega lo suyo con `merge`.

## Variables principales

| Variable | Default | Qué controla |
|---|---|---|
| `name_suffix` | `""` (aleatorio) | Sufijo de los nombres globalmente únicos: buckets y dominio de Cognito |
| `single_nat_gateway` | `true` | 1 NAT compartido o uno por AZ |
| `az_count` | `2` | Zonas de disponibilidad (validado: 2 o 3) |
| `api_desired_count` | `2` | Tareas de Fargate de la API |
| `api_cpu_architecture` | `X86_64` | `ARM64` si se aplica desde una Mac con Apple Silicon (el build no emula) |
| `redis_replicas` | `1` | Réplicas de Redis; con 0 se apaga Multi-AZ |
| `create_opensearch_service_linked_role` | `false` | Crear el service-linked role de OpenSearch (ver Problemas conocidos) |
| `run_seed` | `true` | Cargar los datos de demo al final del apply |

Lista completa con descripciones en [`variables.tf`](variables.tf).

## Funciones de Terraform usadas

| Función | Dónde | Para qué |
|---|---|---|
| `cidrsubnet` | `network/main.tf` | Calcular las 6 subnets /24 a partir del CIDR de la VPC |
| `coalesce`, `lower` | `locals.tf` | Usar `name_suffix` o, si está vacío, el sufijo aleatorio |
| `slice` | `locals.tf` | Tomar las primeras `az_count` zonas disponibles |
| `substr` | `network/main.tf`, `compute/ecr.tf` | Nombre de subnet por zona (`1a`) y tag corto de la imagen |
| `jsonencode` | `storage`, `database`, `compute`, `main.tf` | Bucket policy, access policy de OpenSearch, container definitions, `CORS_ORIGINS` |
| `merge` | `main.tf` | Entorno de la API = entorno común + variables propias |
| `format` | `database/outputs.tf` | Armar `rediss://host:puerto/0` |
| `sha1`, `filesha1`, `fileset`, `sort`, `join` | `compute/ecr.tf`, `lambda_package` | Hash del código: cambia → nueva imagen / nuevo zip |
| `fileexists`, `timestamp` | `lambda_package` | Rearmar el zip si falta el directorio de build |
| `distinct`, `concat`, `flatten`, `values` | `database/dynamodb.tf` | Lista de atributos de la tabla a partir de los GSIs |
| `split` | `compute/ecr.tf` | Host del registry de ECR para el `docker login` |
| `replace` | `network/security_groups.tf` | Descripción de cada regla a partir de su clave |
| `trimsuffix` | `outputs.tf` | URL base del puente |
| `toset`, `tostring`, `contains`, `can`, `regex` | varios | Conversiones y validaciones de variables |

## Meta-argumentos usados

| Meta-argumento | Dónde | Para qué |
|---|---|---|
| `for_each` | security groups y reglas, buckets y sus configuraciones, gateway endpoints, rutas del API Gateway | Un recurso por elemento de un mapa/conjunto, sin repetir bloques |
| `count` | `aws_iam_service_linked_role.opensearch`, `terraform_data.seed` | Recursos opcionales encendidos por una variable booleana |
| `depends_on` | bucket policy → public access block; servicio ECS → listener; task definition → push de la imagen; `archive_file` → build; dominio → service-linked role; seed → servicio | Dependencias que no surgen de una referencia |
| `lifecycle` | `create_before_destroy` en security groups y target group; `ignore_changes = [schema]` en el User Pool | Reemplazos sin corte; no recrear el pool (borraría las cuentas) |

También se usan bloques `dynamic` (atributos y GSIs de DynamoDB, schema de Cognito) y
`validation` en variables.

## Ejecución paso a paso

### Requisitos

- Terraform ≥ 1.6, AWS CLI v2, Docker (corriendo), Python 3 con `pip`.
- Un Learner Lab iniciado (círculo verde).

### 1. Credenciales

En el Learner Lab: **AWS Details → AWS CLI → Show**, y pegar el bloque en
`~/.aws/credentials` (perfil `default`). Vencen con la sesión (~4 h): si un comando falla con
`ExpiredToken`, se vuelven a copiar.

```bash
aws sts get-caller-identity    # tiene que mostrar el rol voclabs
```

### 2. Configuración (opcional)

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # ajustar si hace falta
```

En una Mac con Apple Silicon conviene `api_cpu_architecture = "ARM64"`.

### 3. Despliegue

```bash
terraform init
terraform validate
terraform plan -out tfplan
terraform apply tfplan
```

Tarda ~25 minutos; lo más lento es OpenSearch (~15 min) y ElastiCache (~10 min). Si se corta
(credenciales vencidas), renovarlas y volver a correr `terraform apply`: converge.

### 4. Frontend

Vite hornea las URLs en el build, así que va después del apply:

```bash
terraform output -raw frontend_env > ../frontend/.env.production
cd ../frontend
npm install && npm run build
aws s3 sync dist/ "s3://$(cd ../terraform && terraform output -raw frontend_bucket)" --delete
```

### 5. Verificación

```bash
terraform output frontend_url       # la plataforma
curl "$(terraform output -raw api_url)/health"
```

`/health` tiene que devolver `ok` en `cache`, `storage` y `search`. Usuarios de demo: los de la
tabla del [README principal](../README.md) (`admin@bookup.example` / `bookup123`, etc.).

### 6. Desarme

```bash
terraform destroy
```

Los buckets y el repositorio de ECR se borran aunque tengan contenido (`force_destroy`).

## Problemas conocidos

- **Service-linked role de OpenSearch.** Un dominio en VPC lo necesita. Si el apply falla con
  *"Before you can proceed, you must enable a service-linked role"*, correr con
  `create_opensearch_service_linked_role = true`. Si dice que el rol ya existe, dejarlo en `false`.
- **El state tiene el client secret de Cognito.** `terraform.tfstate` está en `.gitignore`;
  nunca se commitea. Para compartirlo, el backend S3 comentado en `versions.tf`.
- **Costo.** NAT, ALB, Fargate, ElastiCache y OpenSearch cobran por hora (~USD 4,5/día en total). Hacer
  `terraform destroy` al terminar.
