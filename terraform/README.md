# BookUp — Infraestructura como código (Terraform)

Despliega BookUp completo en una cuenta de AWS Academy (Learner Lab). Qué se crea y por qué:
[`../arquitectura-explain.md`](../arquitectura-explain.md).

## Estructura

```
terraform/
  organization/             # configuración raíz: lo que Terraform ejecuta
    versions.tf             # Terraform, providers (aws ~> 6.0, archive, random) y backend S3
    providers.tf            # provider aws con default_tags
    variables.tf            # parámetros del despliegue (todos con default)
    locals.tf               # sufijo único, AZs, tags, rutas del repo
    data.tf                 # LabRole, cuenta, AZs disponibles
    main.tf                 # composición de los módulos
    outputs.tf              # URLs, ids de Cognito y el .env del frontend
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
| [`network`](modules/network/README.md) | Propio | Envuelve el módulo externo + 5 security groups + reglas + endpoints S3/DynamoDB | `vpc_cidr`, `azs`, `single_nat_gateway` → `vpc_id`, subnets, `security_group_ids` |
| [`storage`](modules/storage/README.md) | Propio | 2 buckets (alta/baja por CLI) con ownership, cifrado, acceso público, policy, website, CORS, y versionado + lifecycle en covers | `suffix` → `frontend_url`, nombres de bucket |
| [`database`](modules/database/README.md) | Propio | Tabla DynamoDB con 4 GSIs y stream, replication group de Redis | subnets de datos, SG → `table_name`, `table_stream_arn`, `redis_url` |
| [`search`](modules/search/README.md) | Propio | NLB interno, target group, task definition y servicio de Fargate con OpenSearch | subnets privadas, SGs, cluster → `url` (espera a que el servicio esté sano) |
| [`lambda_package`](modules/lambda_package/README.md) | Propio, reutilizable | `terraform_data` que corre `build.sh` + `archive_file` | `source_dir` → `zip_path`, `zip_hash` |
| [`auth`](modules/auth/README.md) | Propio | User Pool, dominio, app client, 2 Lambdas, HTTP API con 2 rutas, permisos de invocación | `frontend_url`, zip de la API → `user_pool_id`, `client_id`, `cognito_domain`, URLs del puente |
| [`indexer`](modules/indexer/README.md) | Propio | Lambda en VPC, SQS DLQ, event source mapping | zip, `stream_arn`, entorno → `dlq_url` |
| [`compute`](modules/compute/README.md) | Propio | ECR + lifecycle, push de la imagen, ALB/TG/listener, task definition, servicio, seed | subnets, SGs, cluster, entorno → `api_url`, `image_uri`, `reindex_command` |

`lambda_package` se usa una vez y su zip lo consumen dos módulos (`auth` e `indexer`), que
corren el mismo código de `api/`. El entorno común de la API y del indexador se arma una sola
vez en `main.tf` (`local.shared_environment`) y la API le agrega lo suyo con `merge`.

Cada módulo propio tiene un `README.md` con sus inputs, outputs y recursos, generado con
[terraform-docs](https://terraform-docs.io) entre las marcas `<!-- BEGIN_TF_DOCS -->` y
`<!-- END_TF_DOCS -->`. No se edita a mano: si cambian las variables o los outputs de un
módulo, se regenera (lo mismo hace el workflow de docs en cada PR):

```bash
for d in terraform/modules/*/; do
  terraform-docs markdown table --output-file README.md --output-mode inject "$d"
done
```

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
| `covers_noncurrent_days` | `30` | Días que se conservan las versiones anteriores de las portadas |

Lista completa con descripciones en [`variables.tf`](organization/variables.tf).

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
cd terraform/organization
cp terraform.tfvars.example terraform.tfvars   # ajustar si hace falta
```

En una Mac con Apple Silicon conviene `api_cpu_architecture = "ARM64"`.

### 3. Despliegue

El state vive en un bucket S3 (backend remoto). El bucket se nombra por convención
`bookup-tfstate-<account_id>`; crealo una vez (o dejá que lo cree el pipeline):

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb "s3://bookup-tfstate-$ACCOUNT_ID" --region us-east-1

terraform init -backend-config="bucket=bookup-tfstate-$ACCOUNT_ID"
terraform validate
terraform plan -out tfplan
terraform apply tfplan
```

Para solo validar/planear sin tocar el backend: `terraform init -backend=false` (y `validate`).

Tarda ~20 minutos; lo más lento es ElastiCache (~10 min). Si se corta
(credenciales vencidas), renovarlas y volver a correr `terraform apply`: converge.

### 4. Frontend

Vite hornea las URLs en el build, así que va después del apply:

```bash
terraform output -raw frontend_env > ../../frontend/.env.production
cd ../../frontend
npm install && npm run build
BUCKET=$(cd ../terraform/organization && terraform output -raw frontend_bucket)
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

## Pipeline de GitHub Actions

El workflow [`terraform-deploy.yml`](../.github/workflows/terraform-deploy.yml) ejecuta
Terraform sobre `terraform/organization`. Está partido en dos para ser seguro y barato:

| Disparador | Job | Pasos | ¿Credenciales? |
|---|---|---|---|
| `pull_request` (automático) | `validate` | `init -backend=false` → `validate` | No. No toca AWS: el check del PR queda verde sin depender de nadie. |
| `workflow_dispatch` (botón "Run workflow") | `plan-apply` | crea el bucket de state → `init` (backend S3) → `validate` → `plan` → `apply` → build y subida del frontend al bucket | Sí: las del Learner Lab, cargadas como *secrets* del repo. `apply` solo corre si se tilda la opción al disparar. |

Así se cubren los cuatro comandos (`init`, `validate`, `plan`, `apply`) sin que el PR
dispare infraestructura real: el `apply` es deliberado (botón + tilde), nunca automático.

### Cómo deployar desde el pipeline

1. Iniciar el Learner Lab y copiar el bloque de **AWS Details → AWS CLI**.
2. En el repo: **Settings → Secrets and variables → Actions → New repository secret**, y cargar
   los tres valores del lab como secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_SESSION_TOKEN`

   (Vencen con la sesión del lab; si vencen, se vuelven a pegar.)
3. **Actions → Terraform Deploy → Run workflow**. Dejar `apply` sin tildar para solo ver el
   `plan`, o tildarlo para desplegar de verdad. Con `apply` tildado, además de crear la
   infraestructura, el workflow **compila el frontend y lo sube al bucket**, así que al
   terminar la plataforma queda servida en `frontend_url` sin pasos manuales.

El state se guarda en `s3://bookup-tfstate-<account_id>` (versionado, privado, con bloqueo
nativo de S3), que el propio workflow crea si no existe.

### Chequeos de cada PR

Además del `validate`, cada PR corre tres workflows:

| Workflow | Qué verifica |
|---|---|
| Terraform Format | `terraform fmt -check -recursive`: correr `terraform fmt -recursive` antes de pushear |
| Terraform Security | Análisis estático con tfsec, con los hallazgos subidos a *Code scanning* |
| Generate terraform docs | Regenera los README de `modules/` y los pushea a la rama del PR |

El workflow de docs hace checkout de la rama del PR **en este repo**: un PR abierto desde un
fork falla en el checkout. La rama se pushea acá y el PR se abre desde ella.

Hallazgos de tfsec que se ignoran a propósito, con un `#tfsec:ignore` justificado al lado:

| Regla | Recurso | Por qué |
|---|---|---|
| `aws-elb-alb-not-public` | `compute/alb.tf`, ALB | Es la entrada pública de la API |
| `aws-elb-http-not-used` | `compute/alb.tf`, listener | Sin dominio propio no hay certificado ACM en Academy |

El resto se resolvió en el código: la DLQ del indexador va cifrada (SSE-SQS), el ALB descarta
headers inválidos, el stage del puente tiene access logs y los tags de ECR son inmutables (el
tag es el hash del código, y `push_image.sh` no vuelve a subir un tag que ya existe).

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
