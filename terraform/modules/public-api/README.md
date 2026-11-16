# Módulo `public-api`

API pública gobernada del catálogo de BookUp (gap del TP1). Un **API Gateway REST** delante
del ALB de la API que expone **solo la lectura** del catálogo a consumidores externos (otras
bibliotecas), con **API keys + usage plan** (throttling y quota por cliente) y **métricas en
CloudWatch**.

## Por qué así

- **REST API (v1), no HTTP API (v2).** Las API keys y los usage plans —el control de terceros
  que pide la consigna— solo existen en REST API. El `auth-bridge` usa un HTTP API y confirma
  que el Learner Lab deja crear API Gateway; acá se usa la variante que trae gobierno.
- **Proxy al ALB, sin VPC link.** El ALB de la API es *internet-facing* (HTTP:80), así que la
  integración es `HTTP_PROXY` directa a su DNS. Un VPC link pediría un NLB; no hace falta.
- **No duplica lógica.** Hace proxy a los mismos endpoints de FastAPI; la paginación, la
  búsqueda y la disponibilidad las resuelve el backend. Este módulo solo pone la puerta
  gobernada adelante.
- **Solo lectura.** Se exponen únicamente los `GET` del catálogo. Nada de escritura ni de login
  de usuarios: eso sigue entrando por el ALB con token de Cognito.

## Endpoints expuestos

| Método y ruta                      | Backend (FastAPI)                  |
| ---------------------------------- | ---------------------------------- |
| `GET /books`                       | listado paginado + filtros         |
| `GET /books/search`                | búsqueda por texto libre           |
| `GET /books/cities`                | ciudades con stock                 |
| `GET /books/{isbn}`                | detalle de un libro                |
| `GET /books/{isbn}/availability`   | disponibilidad por sede            |

El proxy reenvía método, headers y **query string** tal cual; los parámetros de path (`{isbn}`)
se declaran y mapean explícitamente (es lo único que el proxy no infiere solo).

## Gobierno

- **API key por consumidor** (`external_consumers`): cada nombre crea una `aws_api_gateway_api_key`
  ligada al usage plan. Sin una clave válida en el header `x-api-key`, el API responde **403**.
- **Usage plan**: el throttling (`rate_limit`/`burst_limit`) y la quota (`quota_limit`/`period`)
  se cuentan **por API key**, así que son el límite de *cada* cliente. Un consumidor ruidoso no
  afecta al resto.
- **Techo del stage** (`stage_throttle_*`): límite agregado de todas las claves juntas, como red
  de seguridad del backend.
- **Métricas en CloudWatch**: `metrics_enabled` por método (Count, Latency, 4XXError, 5XXError
  por recurso, namespace `AWS/ApiGateway`). No necesita el rol de CloudWatch a nivel cuenta
  (eso solo lo piden los access/execution logs), así que levanta en el lab sin tocar config
  global.

## Uso

```hcl
module "public_api" {
  source = "../modules/public-api"

  name_prefix      = "bookup"
  backend_base_url = module.compute.api_url   # http://<alb-dns>, sin barra final
  external_consumers = ["demo-library", "biblioteca-nacional"]
}
```

## Ejemplo de consumo (demo)

```bash
# 1. URL del catálogo público y valor de la API key (están en los outputs del stack)
API_URL=$(terraform output -raw public_api_url)
API_KEY=$(terraform output -json public_api_keys | jq -r '."demo-library"')

# 2. Listar el catálogo
curl -s -H "x-api-key: $API_KEY" "$API_URL/books?limit=5" | jq

# 3. Buscar, detalle y disponibilidad
curl -s -H "x-api-key: $API_KEY" "$API_URL/books/search?q=borges" | jq
curl -s -H "x-api-key: $API_KEY" "$API_URL/books/9780307474728" | jq
curl -s -H "x-api-key: $API_KEY" "$API_URL/books/9780307474728/availability" | jq

# 4. Sin clave: 403 (así se ve el gobierno)
curl -s -o /dev/null -w '%{http_code}\n' "$API_URL/books"
```

El valor de la clave también se puede sacar sin Terraform, con el id del output `api_key_ids`:

```bash
aws apigateway get-api-key --api-key <KEY_ID> --include-value --query value --output text
```
