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
| Base de datos | DynamoDB, tabla única `bookup`, 4 GSIs, On-Demand, PITR, stream `NEW_AND_OLD_IMAGES`, TTL sobre `ttl_epoch` | Fuente de verdad de todo. El TTL borra las notificaciones a los 90 días (solo ellas llevan el atributo) |
| Búsqueda | OpenSearch 2.17 en Fargate (1 tarea) detrás de un NLB interno :9200 | Listado, búsqueda y filtros del catálogo. No es el servicio gestionado: el Learner Lab no lo permite. El índice es descartable y se reconstruye desde DynamoDB (`reindex_command`) |
| Indexador | Lambda en VPC + event source mapping al stream (filtrado a `BOOK#` y `COPY#`) + DLQ en SQS | Mantiene OpenSearch al día con DynamoDB e invalida el cache |
| Notificador | Lambda fuera de la VPC + event source mapping al stream (filtrado a `RES#` y a los borrados por TTL de `INBOX#`) | Segundo lector del stream: detecta los cambios de cada reserva y los publica en SNS |
| Bus de eventos | SNS `bookup-reservation-events` (estándar, cifrado con `alias/aws/sns`) | Desacopla quién detecta de quién entrega: un canal nuevo (email, analítica) es una suscripción más |
| Bandejas | Lambda `inbox-writer` fuera de la VPC, suscripta al topic | Arma el texto y escribe la notificación del lector y la de la sede en DynamoDB |
| Job de vencimientos | Rule de EventBridge `rate(15 minutes)` + Lambda `deadline-scanner` fuera de la VPC | Marca las reservas con el plazo vencido; el aviso sale por el stream como cualquier otro cambio |
| Reportes | Rule de EventBridge `rate(60 minutes)` + Lambda `analytics-exporter` fuera de la VPC → bucket S3 privado (JSON Lines) → Glue Catalog + Athena (workgroup propio, 4 queries guardadas) | Estadísticas (reservas por sede y mes, libros más pedidos...) sin cargar la app. La Lambda lee por GSI1 y reescribe la foto completa; no exporta datos personales |
| Cache | ElastiCache Redis, primario + 1 réplica Multi-AZ, TLS (`rediss://`) | Cache de lecturas y rate limiting |
| Identidad | Cognito User Pool + dominio de Hosted UI + app client confidencial | Login, registro y recuperación de contraseña |
| Registro | Lambda `post-confirmation` (trigger del pool) | Crea el `User` (`customer`) en DynamoDB al confirmar el registro |
| Puente HTTPS | API Gateway HTTP API + Lambda `auth-bridge` | Cognito solo acepta callbacks HTTPS y el frontend es HTTP: el puente canjea el code por tokens y redirige al frontend |
| Datos de demo | Tarea one-shot de ECS (`app.seed` + `app.seed_cognito`) | Carga sedes, libros, ejemplares, usuarios y las notificaciones de demo, y crea las cuentas en Cognito |

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

## Flujo de notificaciones

API (escribe la reserva) o `deadline-scanner` (escribe la marca «venció el plazo») → DynamoDB →
stream → Lambda `notifier` → SNS → Lambda `inbox-writer` → ítems `INBOX#USER#…` / `INBOX#LIB#…`
de la misma tabla. El frontend pregunta `GET /notifications/unread-count` cada 30 s.

Las tres Lambdas corren fuera de la VPC: solo hablan con DynamoDB y SNS, que son endpoints
públicos, así que no ocupan ENIs ni pasan por el NAT. SNS y EventBridge las invocan con permisos
basados en recursos (`aws_lambda_permission`): no hace falta ningún rol nuevo. Lo que falla tres
veces en el `inbox-writer` queda solo en CloudWatch: se pierde el aviso, nunca la reserva.

## Flujo de reportes

EventBridge (cada hora, o a mano con `analytics_export_command`) → Lambda `analytics-exporter` → lee reservas,
sedes y libros de DynamoDB por GSI1 (sin `Scan`) → reescribe tres archivos JSON Lines en el bucket privado →
Athena los consulta a través de las tablas de Glue. Es una foto completa, no un incremental: reescribir es
idempotente y Athena nunca suma un dato dos veces.

## Qué hace `terraform apply`, en orden

1. Red, security groups y endpoints.
2. Buckets S3, tabla DynamoDB, Redis, y OpenSearch en Fargate (espera a que esté sano).
3. Empaqueta `api/` como zip de Lambda; crea Cognito, el puente, el indexador y las
   notificaciones (topic, Lambdas, mapping y, recién con el mapping listo, la rule del job).
4. Hace `docker build` + `push` de la API a ECR; crea el ALB y el servicio de ECS.
5. Corre la tarea del seed y espera a que termine.

Lo que queda afuera: el build del frontend y la subida al bucket (ver `terraform/README.md`).
