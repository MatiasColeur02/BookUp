# Arquitectura de BookUp en AWS

Qué crea `terraform/` y cómo se conectan las piezas. Región `us-east-1`, cuenta de AWS Academy
(todo usa el rol `LabRole`: no se pueden crear roles IAM).

## Diagrama

**Diagrama de arquitectura:** [`docs/arquitectura.drawio.pdf`](docs/arquitectura.drawio.pdf).

## Componentes

| Componente | Recurso | Para qué |
|---|---|---|
| Red | VPC con 3 capas de subnets × 2 AZ: `public` (ALB, NAT), `private` (ECS, OpenSearch, indexador), `database` (Redis, sin salida a Internet) | Aislar los datos; solo el ALB es público |
| Salida a Internet | 1 NAT Gateway (o uno por AZ con `single_nat_gateway = false`) | La API baja el JWKS de Cognito, llama a su API de administración y baja la imagen de ECR |
| Endpoints de VPC | Gateway endpoints de S3 y DynamoDB | Ese tráfico no pasa por el NAT (es gratis) |
| Frontend | Bucket S3 con website hosting, lectura pública | Sirve la SPA de React (HTTP) |
| Portadas | Bucket S3 público de lectura, con CORS hacia el frontend y versionado (las versiones anteriores se borran a los 30 días) | El browser sube la portada con un PUT firmado por la API y la muestra con `<img>` |
| API | ECR + ECS Fargate (2 tareas) detrás de un ALB HTTP:80 | FastAPI en `AUTH_MODE=cognito`; health check en `/health` |
| Base de datos | DynamoDB, tabla única `bookup`, 4 GSIs, On-Demand, PITR, stream `NEW_AND_OLD_IMAGES` | Fuente de verdad de todo |
| Búsqueda | OpenSearch 2.17 en Fargate (1 tarea) detrás de un NLB interno :9200 | Listado, búsqueda y filtros del catálogo. No es el servicio gestionado: el Learner Lab no lo permite. El índice es descartable y se reconstruye desde DynamoDB (`reindex_command`) |
| Indexador | Lambda en VPC + event source mapping al stream + DLQ en SQS | Mantiene OpenSearch al día con DynamoDB e invalida el cache |
| Cache | ElastiCache Redis, primario + 1 réplica Multi-AZ, TLS (`rediss://`) | Cache de lecturas y rate limiting |
| Identidad | Cognito User Pool + app client **público** (sin secret, flujo `USER_PASSWORD_AUTH`) | Login, registro y recuperación de contraseña desde los formularios propios del frontend, que llaman directo a la API del pool |
| Registro | Lambda `post-confirmation` (trigger del pool) | Crea el `User` (`customer`) en DynamoDB al confirmar el registro |
| Datos de demo | Tarea one-shot de ECS (`app.seed` + `app.seed_cognito`) | Carga sedes, libros, ejemplares y usuarios, y crea sus cuentas en Cognito |

## Seguridad de red

| Security group | Acepta | Desde |
|---|---|---|
| `alb` | TCP 80 | Internet |
| `app` | TCP 8000 | `alb` |
| `redis` | TCP 6379 | `app`, `lambda` |
| `search_nlb` | TCP 9200 | `app`, `lambda` |
| `search` | TCP 9200 | `search_nlb` |
| `lambda` | — (solo salida) | — |

## Flujo de login

1. El usuario completa el formulario de ingreso del frontend (no hay Hosted UI ni redirects).
2. El browser llama a `InitiateAuth` (`USER_PASSWORD_AUTH`) en `https://cognito-idp.us-east-1.amazonaws.com/`. Es HTTPS, así que la contraseña viaja cifrada aunque el frontend sea HTTP, y nunca pasa por la API.
3. Cognito devuelve los tokens; el frontend guarda solo el access token. Si la cuenta tiene contraseña temporal (personal dado de alta por un sysadmin), Cognito pide elegir la definitiva (`RespondToAuthChallenge`).
4. El frontend manda `Authorization: Bearer <token>` al ALB; la API valida la firma contra el JWKS del pool y busca el rol y la sede del usuario en DynamoDB.

El registro es `SignUp` + `ConfirmSignUp` (código por email; al confirmar corre el trigger
`post-confirmation`), y «olvidé mi contraseña» es `ForgotPassword` + `ConfirmForgotPassword`.
El logout solo descarta el token en el browser.

**Por qué `USER_PASSWORD_AUTH` y no SRP:** las implementaciones de SRP usan `crypto.subtle`, que
el browser solo ofrece en HTTPS, y el frontend se sirve por HTTP desde S3.

## Flujo de datos del catálogo

Escritura en la API → DynamoDB → stream → Lambda indexador → OpenSearch (+ invalidación de
Redis). Las lecturas del catálogo salen de OpenSearch (con cache en Redis); el resto, de DynamoDB.

## Qué hace `terraform apply`, en orden

1. Red, security groups y endpoints.
2. Buckets S3, tabla DynamoDB, Redis, y OpenSearch en Fargate (espera a que esté sano).
3. Empaqueta `api/` como zip de Lambda; crea Cognito (pool, app client y trigger) y el indexador.
4. Hace `docker build` + `push` de la API a ECR; crea el ALB y el servicio de ECS.
5. Corre la tarea del seed y espera a que termine.

Lo que queda afuera: el build del frontend y la subida al bucket (ver `terraform/README.md`).
