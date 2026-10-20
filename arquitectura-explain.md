# Arquitectura de BookUp en AWS

Qué crea `terraform/` y cómo se conectan las piezas. Región `us-east-1`, cuenta de AWS Academy
(todo usa el rol `LabRole`: no se pueden crear roles IAM).

## Diagrama

```
 Navegador
   │
   ├─ HTTP ──► S3 frontend (website)        S3 covers (portadas) ◄── HTTP GET / PUT firmado
   │
   ├─ HTTPS ─► Cognito Hosted UI ── trigger ──► Lambda post-confirmation ──► DynamoDB
   │
   ├─ HTTPS ─► API Gateway /callback, /signed-out ──► Lambda auth-bridge
   │
   └─ HTTP ──► ALB :80
                │
┌─ VPC ─────────┼──────────────────────────────────────────────────────────────┐
│ public        │                 NAT Gateway ──► Internet (JWKS, Cognito, ECR) │
│               ▼                      ▲                                        │
│ private   ECS Fargate (API) ─────────┘          Lambda indexer                │
│               │  │  │                             │   │   ▲                   │
│               │  │  └──► NLB ──► OpenSearch ◄─────┘   │   │                   │
│ database      │  │       (Fargate)                    │   │                   │
│               │  └─────► ElastiCache Redis ◄──────────┘   │                   │
│               │                                           │ stream            │
│               └──► gateway endpoints S3 / DynamoDB ──► DynamoDB ──────────────┘
└───────────────────────────────────────────────────────────────────────────────┘
```

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
| Identidad | Cognito User Pool + dominio de Hosted UI + app client confidencial | Login, registro y recuperación de contraseña |
| Registro | Lambda `post-confirmation` (trigger del pool) | Crea el `User` (`customer`) en DynamoDB al confirmar el registro |
| Puente HTTPS | API Gateway HTTP API + Lambda `auth-bridge` | Cognito solo acepta callbacks HTTPS y el frontend es HTTP: el puente canjea el code por tokens y redirige al frontend |
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

1. El frontend redirige a la Hosted UI de Cognito.
2. Cognito vuelve a `https://<api-gateway>/callback?code=…`.
3. La Lambda `auth-bridge` canjea el code (con el client secret) y redirige a `http://<frontend>/#access_token=…`.
4. El frontend manda `Authorization: Bearer <token>` al ALB; la API valida la firma contra el JWKS del pool y busca el rol y la sede del usuario en DynamoDB.

El logout pasa por el `/logout` de Cognito y vuelve por `/signed-out` del mismo puente.

## Flujo de datos del catálogo

Escritura en la API → DynamoDB → stream → Lambda indexador → OpenSearch (+ invalidación de
Redis). Las lecturas del catálogo salen de OpenSearch (con cache en Redis); el resto, de DynamoDB.

## Qué hace `terraform apply`, en orden

1. Red, security groups y endpoints.
2. Buckets S3, tabla DynamoDB, Redis, y OpenSearch en Fargate (espera a que esté sano).
3. Empaqueta `api/` como zip de Lambda; crea Cognito, el puente y el indexador.
4. Hace `docker build` + `push` de la API a ECR; crea el ALB y el servicio de ECS.
5. Corre la tarea del seed y espera a que termine.

Lo que queda afuera: el build del frontend y la subida al bucket (ver `terraform/README.md`).
