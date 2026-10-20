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
    database/               # DynamoDB, ElastiCache Redis
    search/                 # OpenSearch en Fargate detrás de un NLB interno
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
| `storage` | Propio | 2 buckets (alta/baja por CLI) con ownership, cifrado, acceso público, policy, website y CORS | `suffix` → `frontend_url`, nombres de bucket |
| `database` | Propio | Tabla DynamoDB con 4 GSIs y stream, replication group de Redis | subnets de datos, SG → `table_name`, `table_stream_arn`, `redis_url` |
| `search` | Propio | NLB interno, target group, task definition y servicio de Fargate con OpenSearch | subnets privadas, SGs, cluster → `url` (espera a que el servicio esté sano) |
| `lambda_package` | Propio, reutilizable | `terraform_data` que corre `build.sh` + `archive_file` | `source_dir` → `zip_path`, `zip_hash` |
| `auth` | Propio | User Pool, dominio, app client, 2 Lambdas, HTTP API con 2 rutas, permisos de invocación | `frontend_url`, zip de la API → `user_pool_id`, `client_id`, `cognito_domain`, URLs del puente |
| `indexer` | Propio | Lambda en VPC, SQS DLQ, event source mapping | zip, `stream_arn`, entorno → `dlq_url` |
| `compute` | Propio | ECR + lifecycle, push de la imagen, ALB/TG/listener, task definition, servicio, seed | subnets, SGs, cluster, entorno → `api_url`, `image_uri`, `reindex_command` |

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
| `search_cpu` / `search_memory` | `1024` / `2048` | Tamaño de la tarea de OpenSearch (la mitad de la memoria es heap) |
| `run_seed` | `true` | Cargar los datos de demo al final del apply |

Lista completa con descripciones en [`variables.tf`](variables.tf).

## Funciones de Terraform usadas

| Función | Dónde | Para qué |
|---|---|---|
| `cidrsubnet` | `network/main.tf` | Calcular las 6 subnets /24 a partir del CIDR de la VPC |
| `coalesce`, `lower` | `locals.tf` | Usar `name_suffix` o, si está vacío, el sufijo aleatorio |
| `slice` | `locals.tf` | Tomar las primeras `az_count` zonas disponibles |
| `substr` | `network/main.tf`, `compute/ecr.tf` | Nombre de subnet por zona (`1a`) y tag corto de la imagen |
| `jsonencode` | `storage`, `database`, `compute`, `main.tf` | Bucket policy, policy de ECR, container definitions, `CORS_ORIGINS` |
| `merge` | `main.tf` | Entorno de la API = entorno común + variables propias |
| `format`, `floor` | `database/outputs.tf`, `search/main.tf` | Armar `rediss://host:puerto/0`; heap de la JVM = mitad de la memoria |
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
| `count` | `terraform_data.seed` | Recurso opcional encendido por `run_seed` |
| `depends_on` | bucket policy → public access block; servicio ECS → listener; task definition → push de la imagen; `archive_file` → build; servicio de OpenSearch → listener; output `search.url` → servicio sano; seed → servicio | Dependencias que no surgen de una referencia |
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

Tarda ~20 minutos; lo más lento es ElastiCache (~10 min). Si se corta
(credenciales vencidas), renovarlas y volver a correr `terraform apply`: converge.

### 4. Frontend

Vite hornea las URLs en el build, así que va después del apply:

```bash
terraform output -raw frontend_env > ../frontend/.env.production
cd ../frontend
npm install && npm run build
BUCKET=$(cd ../terraform && terraform output -raw frontend_bucket)
aws s3 sync dist/ "s3://$BUCKET" --delete --exclude index.html
# index.html sin cache: si no, el navegador puede seguir pidiendo el bundle anterior.
aws s3 cp dist/index.html "s3://$BUCKET/index.html" --cache-control no-cache
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

- **OpenSearch no es el servicio gestionado.** El Learner Lab deniega `es:CreateDomain` y Cloud
  Map, así que OpenSearch corre como contenedor en Fargate (la misma imagen del docker-compose)
  detrás de un NLB interno. El índice está en el disco efímero de la tarea: si la tarea se
  reemplaza, el catálogo queda vacío hasta correr `terraform output -raw reindex_command | sh`.
  La fuente de verdad es DynamoDB, así que no se pierde nada.
- **Los buckets se crean con la CLI.** El recurso `aws_s3_bucket` lee la configuración de Object
  Lock en cada refresh y el Learner Lab la deniega con una SCP
  (`s3:GetBucketObjectLockConfiguration`). Por eso el bucket lo crea y lo borra un
  `terraform_data` (`modules/storage/bucket.sh`, idempotente) y el resto de su configuración
  (website, policy, CORS, cifrado) son recursos nativos.
- **El state tiene el client secret de Cognito.** `terraform.tfstate` está en `.gitignore`;
  nunca se commitea. Para compartirlo, el backend S3 comentado en `versions.tf`.
- **Costo.** NAT, ALB, Fargate, ElastiCache y OpenSearch cobran por hora (~USD 4,5/día en total). Hacer
  `terraform destroy` al terminar.
